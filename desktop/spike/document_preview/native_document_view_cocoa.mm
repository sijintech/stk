/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "native_document_view.hh"

#import <AppKit/AppKit.h>
#import <WebKit/WebKit.h>

#include <algorithm>
#include <memory>
#include <utility>

namespace stk::document_preview::cocoa {

struct State {
  std::shared_ptr<ResourceSession> resources;
  NativeViewState result;
  __weak NSWindow *parent = nil;
  __strong WKWebView *view = nil;
  __strong NSObject *delegate = nil;
  __strong WKNavigation *navigation = nil;
  std::string requested_url;
  bool closed = false;
  bool policy_ready = false;
  bool policy_failed = false;
  bool visible = false;
  bool has_bounds = false;
};

static NSString *string(std::string_view value)
{
  return [[NSString alloc] initWithBytes:value.data()
                                 length:value.size()
                               encoding:NSUTF8StringEncoding];
}

static std::string utf8(NSString *value)
{
  const char *bytes = value.UTF8String;
  return bytes ? std::string(bytes) : std::string();
}

static bool live(const std::shared_ptr<State> &state)
{
  return state && !state->closed && state->parent && state->resources->active();
}

static bool admitted_url(const std::shared_ptr<State> &state, std::string_view url)
{
  // ResourceSession also understands the Windows HTTPS form; WK must never fetch that URL.
  return url.starts_with("stk-preview://local/") && state->resources->allows_navigation(url);
}

static void blocked(const std::shared_ptr<State> &state)
{
  if (state && !state->closed) {
    ++state->result.blocked_requests;
  }
}

static void fail(const std::shared_ptr<State> &state, const char *message)
{
  state->result.status = NativeViewStatus::Failed;
  state->result.message = message;
}

static void relinquish_focus(const std::shared_ptr<State> &state)
{
  NSWindow *parent = state->parent;
  NSResponder *responder = parent.firstResponder;
  if ([responder isKindOfClass:[NSView class]] &&
      (responder == state->view || [(NSView *)responder isDescendantOf:state->view])) {
    if (![parent makeFirstResponder:parent.contentView]) {
      [parent makeFirstResponder:nil];
    }
  }
}

static void sync_visibility(const std::shared_ptr<State> &state)
{
  const bool show = live(state) && state->visible && state->has_bounds;
  if (!show) {
    relinquish_focus(state);
  }
  state->view.hidden = !show;
}

// All calls and delegate callbacks are on the main thread. The returned WKNavigation is the
// identity of this load; a cancelled older load may still report its failure afterwards.
static void load_requested(const std::shared_ptr<State> &state)
{
  if (!live(state) || !state->policy_ready || state->requested_url.empty()) {
    return;
  }
  NSURL *url = [NSURL URLWithString:string(state->requested_url)];
  NSURLRequest *request = [NSURLRequest requestWithURL:url
                                         cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                     timeoutInterval:30.0];
  state->navigation = [state->view loadRequest:request];
  if (!state->navigation) {
    fail(state, "WKWebView did not accept the document load.");
  }
}

static void begin_navigation(const std::shared_ptr<State> &state, std::string url)
{
  ++state->result.navigation_generation;
  state->navigation = nil;
  [state->view stopLoading];
  state->requested_url = std::move(url);
  state->result.status = NativeViewStatus::Loading;
  state->result.message = state->policy_ready ? "Loading admitted document bytes." :
                                               "Preparing the offline resource policy.";
  load_requested(state);
}

static bool current(const std::shared_ptr<State> &state,
                    WKWebView *view,
                    WKNavigation *navigation)
{
  return live(state) && state->view == view && navigation && state->navigation == navigation;
}

}  // namespace stk::document_preview::cocoa

// The candidate intentionally has no context menu: WebKit/PDF menu items can otherwise expose
// "download" or "open with" operations outside the document navigation policy. Copy shortcuts
// remain native. Menu/keyboard/PDF behaviour still needs real macOS acceptance.
@interface STKPreviewWebView : WKWebView
@end

@implementation STKPreviewWebView
- (NSView *)hitTest:(NSPoint)point
{
  NSView *hit = [super hitTest:point];
  NSEvent *event = NSApp.currentEvent;
  if (hit && event.window == self.window &&
      (event.type == NSEventTypeRightMouseDown ||
       (event.type == NSEventTypeLeftMouseDown &&
        (event.modifierFlags & NSEventModifierFlagControl)))) {
    // WKContentView is a child: route context-clicks here before it builds a native menu.
    return self;
  }
  return hit;
}
- (NSMenu *)menuForEvent:(NSEvent *)event
{
  return nil;
}
- (void)rightMouseDown:(NSEvent *)event
{
}
- (void)willOpenMenu:(NSMenu *)menu withEvent:(NSEvent *)event
{
  [menu removeAllItems];
}
@end

@interface STKPreviewDelegate : NSObject <WKNavigationDelegate, WKUIDelegate, WKURLSchemeHandler> {
 @public
  std::weak_ptr<stk::document_preview::cocoa::State> state_;
 @private
  NSMutableSet<id<WKURLSchemeTask>> *tasks_;
}
- (void)invalidate;
@end

@implementation STKPreviewDelegate

- (instancetype)init
{
  self = [super init];
  if (self) {
    tasks_ = [NSMutableSet set];
  }
  return self;
}

- (void)invalidate
{
  state_.reset();
  [tasks_ removeAllObjects];
}

- (void)webView:(WKWebView *)webView startURLSchemeTask:(id<WKURLSchemeTask>)task
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  if (!live(state) || state->view != webView) {
    [task didFailWithError:[NSError errorWithDomain:NSURLErrorDomain
                                             code:NSURLErrorCancelled
                                         userInfo:nil]];
    return;
  }
  [tasks_ addObject:task];
  // ResourceSession never opens a path or contacts a server; only admitted immutable bytes are
  // copied here. No task is queued onto another thread. WebKit may reenter stop during callbacks.
  const auto method = utf8(task.request.HTTPMethod);
  const auto response = state->resources->read(utf8(task.request.URL.absoluteString), method);
  if (response.status != 200) {
    blocked(state);
  }
  NSMutableDictionary *headers = [@{
    @"Content-Type" : string(response.mime),
    @"Content-Security-Policy" : string(response.content_security_policy),
    @"Cache-Control" : @"no-store",
    @"X-Content-Type-Options" : @"nosniff",
    @"Referrer-Policy" : @"no-referrer",
    @"Permissions-Policy" : @"camera=(), microphone=(), geolocation=(), fullscreen=()"
  } mutableCopy];
  // HEAD intentionally returns no body; zero bytes is not the entity's Content-Length.
  if (method != "HEAD") {
    headers[@"Content-Length"] = [NSString stringWithFormat:@"%llu",
                                                          (unsigned long long)response.bytes.size()];
  }
  NSHTTPURLResponse *reply = [[NSHTTPURLResponse alloc] initWithURL:task.request.URL
                                                      statusCode:response.status
                                                     HTTPVersion:@"HTTP/1.1"
                                                    headerFields:headers];
  if (![tasks_ containsObject:task] || !live(state)) {
    return;
  }
  [task didReceiveResponse:reply];
  if (![tasks_ containsObject:task] || !live(state)) {
    return;
  }
  if (!response.bytes.empty()) {
    [task didReceiveData:[NSData dataWithBytes:response.bytes.data() length:response.bytes.size()]];
  }
  if (![tasks_ containsObject:task] || !live(state)) {
    return;
  }
  // Remove before the terminal callback so any reentrant stop cannot resurrect this task.
  [tasks_ removeObject:task];
  [task didFinish];
}

- (void)webView:(WKWebView *)webView stopURLSchemeTask:(id<WKURLSchemeTask>)task
{
  // Apple forbids every task callback after stop, including didFailWithError.
  [tasks_ removeObject:task];
}

- (void)webView:(WKWebView *)webView
    decidePolicyForNavigationAction:(WKNavigationAction *)action
                        preferences:(WKWebpagePreferences *)preferences
                    decisionHandler:(void (^)(WKNavigationActionPolicy,
                                               WKWebpagePreferences *))decisionHandler
{
  using namespace stk::document_preview::cocoa;
  preferences.allowsContentJavaScript = NO;
  auto state = state_.lock();
  const auto url = utf8(action.request.URL.absoluteString);
  const bool allowed = live(state) && state->view == webView && state->policy_ready &&
                       action.targetFrame.isMainFrame && !action.shouldPerformDownload &&
                       [action.request.HTTPMethod isEqualToString:@"GET"] &&
                       admitted_url(state, url);
  if (allowed && action.navigationType == WKNavigationTypeOther &&
      url == state->requested_url) {
    decisionHandler(WKNavigationActionPolicyAllow, preferences);
    return;
  }
  // Reissue an admitted user link as a tracked load. Do not let redirects, forms, new windows,
  // subframes or automatic document navigation create an untracked source identity.
  if (allowed && action.navigationType == WKNavigationTypeLinkActivated) {
    const auto generation = state->result.navigation_generation;
    std::weak_ptr<State> weak = state;
    decisionHandler(WKNavigationActionPolicyCancel, preferences);
    dispatch_async(dispatch_get_main_queue(), ^{
      auto target = weak.lock();
      if (live(target) && target->result.navigation_generation == generation &&
          admitted_url(target, url)) {
        begin_navigation(target, url);
      }
    });
    return;
  }
  blocked(state);
  decisionHandler(WKNavigationActionPolicyCancel, preferences);
}

- (void)webView:(WKWebView *)webView
    decidePolicyForNavigationResponse:(WKNavigationResponse *)response
                     decisionHandler:(void (^)(WKNavigationResponsePolicy))decisionHandler
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  NSHTTPURLResponse *http = [response.response isKindOfClass:[NSHTTPURLResponse class]] ?
                               (NSHTTPURLResponse *)response.response :
                               nil;
  // A custom scheme may be surfaced as NSURLResponse rather than NSHTTPURLResponse. The exact
  // admitted URL still has to resolve in our immutable manifest, independently of that wrapper.
  const bool allowed = live(state) && state->view == webView && response.isForMainFrame &&
                       response.canShowMIMEType && (!http || http.statusCode == 200) &&
                       admitted_url(state, utf8(response.response.URL.absoluteString));
  if (!allowed) {
    blocked(state);
  }
  decisionHandler(allowed ? WKNavigationResponsePolicyAllow : WKNavigationResponsePolicyCancel);
}

- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  if (current(state, webView, navigation)) {
    state->result.status = stk::document_preview::NativeViewStatus::Ready;
    state->result.message = "WKWebView navigation completed; display and input require native acceptance.";
  }
}

- (void)webView:(WKWebView *)webView
    didFailProvisionalNavigation:(WKNavigation *)navigation
                      withError:(NSError *)error
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  if (current(state, webView, navigation)) {
    // Do not copy WebKit diagnostics containing local resource URLs into public state/logs.
    fail(state, "WKWebView could not load the admitted document.");
  }
}

- (void)webView:(WKWebView *)webView
    didFailNavigation:(WKNavigation *)navigation
            withError:(NSError *)error
{
  [self webView:webView didFailProvisionalNavigation:navigation withError:error];
}

- (void)webViewWebContentProcessDidTerminate:(WKWebView *)webView
{
  using namespace stk::document_preview::cocoa;
  auto state = state_.lock();
  if (live(state) && state->view == webView) {
    state->navigation = nil;
    fail(state, "The WebKit content process exited; reopen the document explicitly.");
  }
}

- (void)webView:(WKWebView *)webView
    didReceiveAuthenticationChallenge:(NSURLAuthenticationChallenge *)challenge
                   completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition,
                                                NSURLCredential *))completionHandler
{
  stk::document_preview::cocoa::blocked(state_.lock());
  completionHandler(NSURLSessionAuthChallengeCancelAuthenticationChallenge, nil);
}

- (void)webView:(WKWebView *)webView
    navigationAction:(WKNavigationAction *)action
   didBecomeDownload:(WKDownload *)download
{
  stk::document_preview::cocoa::blocked(state_.lock());
  [download cancel:nil];
}

- (void)webView:(WKWebView *)webView
    navigationResponse:(WKNavigationResponse *)response
     didBecomeDownload:(WKDownload *)download
{
  stk::document_preview::cocoa::blocked(state_.lock());
  [download cancel:nil];
}

- (WKWebView *)webView:(WKWebView *)webView
    createWebViewWithConfiguration:(WKWebViewConfiguration *)configuration
              forNavigationAction:(WKNavigationAction *)action
                   windowFeatures:(WKWindowFeatures *)features
{
  stk::document_preview::cocoa::blocked(state_.lock());
  return nil;
}

- (void)webView:(WKWebView *)webView
    runOpenPanelWithParameters:(WKOpenPanelParameters *)parameters
             initiatedByFrame:(WKFrameInfo *)frame
            completionHandler:(void (^)(NSArray<NSURL *> *))completionHandler
{
  stk::document_preview::cocoa::blocked(state_.lock());
  completionHandler(nil);
}

- (void)webView:(WKWebView *)webView
    requestMediaCapturePermissionForOrigin:(WKSecurityOrigin *)origin
                         initiatedByFrame:(WKFrameInfo *)frame
                                     type:(WKMediaCaptureType)type
                          decisionHandler:(void (^)(WKPermissionDecision))decisionHandler
{
  stk::document_preview::cocoa::blocked(state_.lock());
  decisionHandler(WKPermissionDecisionDeny);
}

- (void)webView:(WKWebView *)webView
    runJavaScriptAlertPanelWithMessage:(NSString *)message
                     initiatedByFrame:(WKFrameInfo *)frame
                    completionHandler:(void (^)(void))completionHandler
{
  completionHandler();
}

- (void)webView:(WKWebView *)webView
    runJavaScriptConfirmPanelWithMessage:(NSString *)message
                       initiatedByFrame:(WKFrameInfo *)frame
                      completionHandler:(void (^)(BOOL))completionHandler
{
  completionHandler(NO);
}

- (void)webView:(WKWebView *)webView
    runJavaScriptTextInputPanelWithPrompt:(NSString *)prompt
                             defaultText:(NSString *)defaultText
                        initiatedByFrame:(WKFrameInfo *)frame
                       completionHandler:(void (^)(NSString *))completionHandler
{
  completionHandler(nil);
}

@end

namespace stk::document_preview {
namespace {

class CocoaDocumentView final : public NativeDocumentView {
 public:
  explicit CocoaDocumentView(std::shared_ptr<cocoa::State> state) : state_(std::move(state)) {}
  ~CocoaDocumentView() override { close(); }

  bool navigate(std::string_view asset_path, std::string &error) override
  {
    error.clear();
    if (!cocoa::live(state_) || state_->policy_failed) {
      error = "The preview is closed or its offline policy is unavailable.";
      return false;
    }
    const auto url = state_->resources->url(asset_path, false);
    if (url.empty()) {
      error = "The document is not in the current preview resource manifest.";
      return false;
    }
    cocoa::begin_navigation(state_, url);
    return true;
  }

  void set_bounds(ViewBounds bounds) override
  {
    if (!cocoa::live(state_)) {
      return;
    }
    NSView *content = state_->parent.contentView;
    const NSRect backing = [content convertRectToBacking:content.bounds];
    const CGFloat width = std::max(bounds.width, 0);
    const CGFloat height = std::max(bounds.height, 0);
    const CGFloat y = content.isFlipped ? NSMaxY(backing) - bounds.y - height :
                                         NSMinY(backing) + bounds.y;
    const NSRect pixels = NSMakeRect(NSMinX(backing) + bounds.x, y, width, height);
    const NSRect frame = NSIntersectionRect([content convertRectFromBacking:pixels], content.bounds);
    state_->has_bounds = !NSIsEmptyRect(frame);
    state_->view.frame = frame;
    cocoa::sync_visibility(state_);
  }

  void set_visible(bool visible) override
  {
    if (!state_->closed) {
      state_->visible = visible;
      cocoa::sync_visibility(state_);
    }
  }

  void focus() override
  {
    if (cocoa::live(state_) && state_->visible && state_->has_bounds) {
      [state_->parent makeFirstResponder:state_->view];
    }
  }

  void close() override
  {
    if (state_->closed) {
      return;
    }
    state_->closed = true;
    ++state_->result.navigation_generation;
    state_->result.status = NativeViewStatus::Closed;
    state_->result.message = "Document preview closed.";
    state_->resources->close();
    state_->navigation = nil;
    cocoa::relinquish_focus(state_);
    state_->view.hidden = YES;
    [(STKPreviewDelegate *)state_->delegate invalidate];
    [state_->view stopLoading];
    state_->view.navigationDelegate = nil;
    state_->view.UIDelegate = nil;
    [state_->view removeFromSuperview];
    state_->view = nil;
    state_->delegate = nil;
    state_->parent = nil;
    state_->requested_url.clear();
  }

  NativeViewState state() const override
  {
    auto result = state_->result;
    NSWindow *parent = state_->parent;
    WKWebView *view = state_->view;
    result.parent_attached = !state_->closed && parent && view &&
                             view.superview == parent.contentView && view.window == parent;
    result.visible = result.parent_attached && !view.isHiddenOrHasHiddenAncestor &&
                     !NSIsEmptyRect(view.visibleRect) && parent.isVisible && !parent.isMiniaturized;
    if (!state_->closed && !cocoa::live(state_)) {
      result.status = NativeViewStatus::Failed;
      result.message = "The parent window or preview resource session is no longer available.";
    }
    return result;
  }

 private:
  std::shared_ptr<cocoa::State> state_;
};

}  // namespace

std::unique_ptr<NativeDocumentView> create_native_document_view(
    wm::NativeWindowHandle parent, std::shared_ptr<ResourceSession> resources, std::string &error)
{
  error.clear();
  if (![NSThread isMainThread] || parent.kind != wm::NativeWindowKind::Cocoa || !parent.value ||
      !resources || !resources->active()) {
    error = "WKWebView requires a live Cocoa parent and resource session on the main thread.";
    return nullptr;
  }
  NSWindow *window = (__bridge NSWindow *)parent.value;
  if (!window.contentView) {
    error = "The Cocoa parent has no content view.";
    return nullptr;
  }
  auto state = std::make_shared<cocoa::State>();
  state->resources = std::move(resources);
  state->parent = window;
  state->result.message = "Preparing the offline resource policy.";
  NSBundle *webkit = [NSBundle bundleForClass:[WKWebView class]];
  state->result.runtime_version = cocoa::utf8([webkit objectForInfoDictionaryKey:@"CFBundleVersion"]);
  STKPreviewDelegate *delegate = [[STKPreviewDelegate alloc] init];
  delegate->state_ = state;
  state->delegate = delegate;
  WKWebViewConfiguration *configuration = [[WKWebViewConfiguration alloc] init];
  configuration.websiteDataStore = [WKWebsiteDataStore nonPersistentDataStore];
  configuration.defaultWebpagePreferences.allowsContentJavaScript = NO;
  configuration.preferences.javaScriptCanOpenWindowsAutomatically = NO;
  configuration.allowsAirPlayForMediaPlayback = NO;
  configuration.mediaTypesRequiringUserActionForPlayback = WKAudiovisualMediaTypeAll;
  [configuration setURLSchemeHandler:delegate forURLScheme:@"stk-preview"];
  state->view = [[STKPreviewWebView alloc] initWithFrame:NSZeroRect configuration:configuration];
  if (!state->view) {
    error = "WKWebView could not be created.";
    return nullptr;
  }
  state->view.navigationDelegate = delegate;
  state->view.UIDelegate = delegate;
  state->view.allowsBackForwardNavigationGestures = NO;
  state->view.allowsLinkPreview = NO;
  state->view.inspectable = NO;
  state->view.hidden = YES;
  [window.contentView addSubview:state->view];

  // Compile a constant, non-project-specific rule list. The store may persist compiled rules;
  // website data stays nonpersistent. No resource URL or project content enters that store.
  // The manifest handler gates the sole allowed scheme; CSP independently forbids active content.
  NSString *rules = @"[{\"trigger\":{\"url-filter\":\".*\"},\"action\":{\"type\":\"block\"}},"
                    "{\"trigger\":{\"url-filter\":\"^stk-preview://local/\"},"
                    "\"action\":{\"type\":\"ignore-previous-rules\"}}]";
  std::weak_ptr<cocoa::State> weak = state;
  [[WKContentRuleListStore defaultStore]
      compileContentRuleListForIdentifier:@"org.stk.document-preview.offline.v1"
                  encodedContentRuleList:rules
                       completionHandler:^(WKContentRuleList *list, NSError *compile_error) {
                         dispatch_async(dispatch_get_main_queue(), ^{
                           auto target = weak.lock();
                           if (!cocoa::live(target)) {
                             return;
                           }
                           if (compile_error || !list) {
                             target->policy_failed = true;
                             cocoa::fail(target, "The offline resource policy could not be installed.");
                             return;
                           }
                           [target->view.configuration.userContentController addContentRuleList:list];
                           target->policy_ready = true;
                           cocoa::load_requested(target);
                         });
                       }];
  return std::make_unique<CocoaDocumentView>(std::move(state));
}

}  // namespace stk::document_preview

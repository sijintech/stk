/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <gtest/gtest.h>

#include "stk/app/project_reports.hh"
#include "stk/app/project_state.hh"
#include "stk/app/script_state.hh"
#include "stk/app/viewer_state.hh"
#include "stk/bridge/process.hh"
#include "stk/core/sha256.hh"
#include "stk/io/payload.hh"
#include "stk/io/png.hh"
#include "../bridge/support.hh"
#include "../wm/support.hh"

#include <cstdlib>
#include <filesystem>
#include <fstream>

namespace stk::app {
namespace {
using io::Json;
namespace fs = std::filesystem;
const std::string report_id = "a1111111-1111-4111-8111-111111111111";
const std::string text_report_id = "b2222222-2222-4222-8222-222222222222";
const std::string pdf_report_id = "c3333333-3333-4333-8333-333333333333";

// Keep real services and strict schema validation. Faults retain valid wire shapes so the
// controller must independently bind every receipt. Hold replies only after service locks end.
constexpr const char *kPreviewBridge = R"PY(
import base64
import hashlib
import os
from pathlib import Path
import sys
import threading
import time
from suan.project import report_previews
from suan.project.reports import Reports
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.__main__ import main
control = Path(sys.argv.pop(1))
def mode():
    return control.read_text(encoding='utf-8') if control.exists() else ''
def count(name):
    with control.with_suffix('.calls').open('a', encoding='utf-8') as output:
        output.write(name + '\n')
prepare = report_previews.preview_resources
def altered_prepare(*args, **kwargs):
    result = prepare(*args, **kwargs)
    p = result['preview']
    current = mode()
    if current == 'source_hash': p['source_content_sha256'] = '0' * 64
    if current == 'render_bytes': p['data'] = base64.b64encode(b'x' * p['size']).decode('ascii')
    if current == 'noncanonical':
        result['total_size'] += 1 - p['size']
        p.update(size=1, data='AB==', content_sha256=hashlib.sha256(b'\x00').hexdigest())
    if current == 'project': p['project_id'] = '00000000-0000-4000-8000-000000000000'
    if current == 'resource_hash': result['resources'][0]['sha256'] = '0' * 64
    if current == 'omitted': result['total_size'] -= result['resources'].pop()['size']
    if current == 'reordered': result['resources'].reverse()
    if current == 'total': result['total_size'] += 1
    return result
report_previews.preview_resources = altered_prepare
identity_preview = report_previews.preview
def altered_identity(*args, **kwargs):
    p = identity_preview(*args, **kwargs)
    current = mode()
    if current == 'pdf_project': p['project_id'] = '00000000-0000-4000-8000-000000000000'
    if current == 'pdf_report': p['report_id'] = '00000000-0000-4000-8000-000000000000'
    if current == 'pdf_manifest': p['source_sha256'] = '0' * 64
    if current == 'pdf_revision': p['revision'] += 1
    if current == 'pdf_path': p['path'] = 'other.pdf'
    if current == 'pdf_mime': p['mime'] = 'image/png'
    if current == 'pdf_source_mime': p['source_mime'] = 'text/html; charset=utf-8'
    if current == 'pdf_renderer': p['renderer'] = 'stk.report-renderer/1'
    if current == 'pdf_source_hash': p['source_content_sha256'] = '0' * 64
    if current == 'pdf_display_hash': p['content_sha256'] = '0' * 64
    if current == 'pdf_size': p['size'] -= 1
    if current == 'pdf_source_size': p['source_size'] -= 1
    if current == 'pdf_bytes': p['data'] = base64.b64encode(b'x' * p['size']).decode('ascii')
    if current == 'pdf_noncanonical':
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        encoded = p['data']
        padding = len(encoded) - len(encoded.rstrip('='))
        assert padding
        index = len(encoded) - padding - 1
        p['data'] = encoded[:index] + alphabet[alphabet.index(encoded[index]) | 1] + encoded[index + 1:]
    return p
report_previews.preview = altered_identity
read = Reports.asset
def altered_asset(self, *args, **kwargs):
    result = read(self, *args, **kwargs)
    if result['mime'].startswith('image/'):
        if mode() == 'image_bytes': result['data'] = base64.b64encode(b'x' * result['size']).decode('ascii')
        if mode() == 'image_second_bytes' and result['path'] == 'images/second.png':
            result['data'] = base64.b64encode(b'x' * result['size']).decode('ascii')
        if mode() == 'image_identity': result['report_id'] = '00000000-0000-4000-8000-000000000000'
    return result
Reports.asset = altered_asset
send = Bridge.send
def observed_send(self, message, method=None):
    if method == 'hello' and 'result' in message and mode() == 'old_bridge':
        message['result']['methods'].remove('project.reports.preview_resources')
    if method == 'hello' and 'result' in message and mode() == 'no_identity_preview':
        message['result']['methods'].remove('project.reports.preview')
    if 'result' in message:
        if method == 'project.reports.preview_resources': count('prepare')
        if method == 'project.reports.preview': count('pdf_prepare')
        if method == 'project.reports.asset': count('asset:' + message['result']['path'])
    held = ((method == 'project.reports.preview_resources' and mode() == 'hold_prepare') or
            (method == 'project.reports.preview' and mode() == 'hold_pdf') or
            (method == 'project.catalog' and mode() == 'hold_catalog') or
            (method == 'project.reports.asset' and mode() == 'hold_image') or
            (method == 'project.reports.asset' and mode() == 'hold_second' and
             message.get('result', {}).get('path') == 'images/second.png'))
    if held and 'result' in message:
        control.with_suffix('.held').write_text('ready', encoding='utf-8')
        def deliver():
            deadline = time.monotonic() + 30
            while not control.with_suffix('.release').exists() and time.monotonic() < deadline:
                if control.with_suffix('.crash').exists():
                    os._exit(73)
                time.sleep(.01)
            send(self, message, method)
            control.with_suffix('.sent').write_text('sent', encoding='utf-8')
        threading.Thread(target=deliver, daemon=True).start()
        return
    return send(self, message, method)
Bridge.send = observed_send
main()
)PY";

class ReportsPreviewPython : public ::testing::Test {
 protected:
  bridge::test::TempDir dir{"reports-preview"};
  bridge::test::ManualLoop loop;
  wmtest::AppFixture f{"en", 1, 1440, 1000};
  std::unique_ptr<bridge::Client> client;
  std::unique_ptr<ProjectReports> reports;
  std::shared_ptr<const io::Payload> shown;
  std::string python, source_sha, project_id;
  const std::string markdown = "# Frozen report\n\n![Plot](../images/plot.png)\n\n[Unsafe](secondary.html)\n";
  std::vector<uint8_t> png, second_png, pdf_bytes;
  std::string pdf_sha;
  Json manifest, viewer_state;
  uint64_t camera_serial = 0, payload_serial = 0;
  AppStore &store() { return f.shell->store(); }
  ProjectState &project() { return store().project(); }
  void mode(const std::string &value)
  {
    std::ofstream output(dir.path() / "mode", std::ios::binary); output << value;
    ASSERT_TRUE(output.good());
  }
  void release() { std::ofstream output(dir.path() / "mode.release"); output << "release"; }
  int count(const std::string &operation)
  {
    std::ifstream input(dir.path() / "mode.calls"); std::string line; int result = 0;
    while (std::getline(input, line)) { result += line == operation; }
    return result;
  }
  bool start_client(const std::string &suffix)
  {
    bridge::ClientOptions options;
    options.python.configured = python; options.executor = loop.executor();
    options.state_dir = dir.str() + "/bridge-" + suffix; options.cache_dir = dir.str() + "/cache-" + suffix;
    options.env["PYTHONPATH"] = STK_REPO_ROOT;
    options.env["STK_STATE_DIR"] = dir.str() + "/runtime-" + suffix;
    options.env["STK_PROFILES_FILE"] = dir.str() + "/profiles.json";
    options.env["STK_TOKEN_PLAN_API_KEY"] = ""; options.env["STK_TOKEN_PLAN_MODEL"] = std::nullopt;
    options.strict = options.validate = true;
    options.command = {python, "-u", dir.str() + "/bridge.py", dir.str() + "/mode",
        "--stdio", "--state-dir", options.state_dir, "--cache-dir", options.cache_dir, "--strict"};
    client = bridge::Client::create(options);
    if (!client->start() || !client->wait_ready(60)) { return false; }
    loop.run_ready(); store().set_bridge(client.get()); project().sync();
    return loop.pump_until([&] { return project().ready(); }, 30);
  }
  Json call_on(bridge::Client &sender, const std::string &method, Json params)
  {
    auto response = std::make_shared<std::optional<bridge::Result<Json>>>();
    auto future = sender.call(method, std::move(params));
    future.then([response](auto result) { *response = std::move(result); });
    if (!loop.pump_until([&] { return response->has_value(); }, 30)) {
      future.cancel(); ADD_FAILURE() << method << " timed out"; return nullptr;
    }
    if (!response->value()) { ADD_FAILURE() << method << ": " << response->value().error().describe(); return nullptr; }
    return response->value().value();
  }
  Json call(const std::string &method, Json params) { return call_on(*client, method, std::move(params)); }
  void settle_project()
  {
    ASSERT_TRUE(loop.pump_until([&] { project().sync(); return project().loaded() && !project().busy() && !project().recent_loading(); }, 30))
        << project().error();
  }
  void settle()
  {
    ASSERT_TRUE(loop.pump_until([&] { reports->sync(); return !reports->busy() && !reports->preview_busy() && !project().busy(); }, 30))
        << reports->error() << reports->preview_error();
  }
  void load(const std::string &identity = report_id)
  {
    ASSERT_TRUE(reports->load(identity, identity == report_id ? source_sha : ""));
    ASSERT_NO_FATAL_FAILURE(settle());
    ASSERT_TRUE(reports->selected().is_object()) << reports->error();
    ASSERT_FALSE(reports->prepared_preview());
  }
  void create_pdf(size_t exact_size = 0)
  {
    // Deliberately binary: this tests byte admission, not whether an OS PDF engine renders it.
    const std::string binary = "%PDF-1.4\n%\xE2\xE3\xCF\xD3\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n";
    pdf_bytes.assign(binary.begin(), binary.end());
    if (exact_size) { pdf_bytes.resize(exact_size, 0xff); }
    else if (pdf_bytes.size() % 3 == 0) { pdf_bytes.push_back('\n'); }
    { std::ofstream file(dir.path() / "project/document.pdf", std::ios::binary);
      file.write(reinterpret_cast<const char *>(pdf_bytes.data()), std::streamsize(pdf_bytes.size())); ASSERT_TRUE(file.good()); }
    const auto handle = project().project()->handle;
    const auto revision = project().project()->revision;
    const auto indexed = call("project.files.index", {{"handle", handle}, {"expected_revision", revision},
        {"paths", Json::array({"document.pdf"})}});
    ASSERT_TRUE(indexed.is_object()); const auto id = indexed.at("record_ids").at(0);
    const auto image = manifest.at("assets").at(1).at("record_id");
    const auto snapshot = call("project.snapshots.capture", {{"handle", handle}, {"expected_revision", revision + 1},
        {"record_ids", Json::array({id, image})}});
    ASSERT_TRUE(snapshot.is_object());
    ASSERT_TRUE(call("project.reports.create", {{"handle", handle}, {"name", "Binary PDF"}, {"report_id", pdf_report_id},
        {"snapshot_id", snapshot.at("snapshot").at("id")}, {"entry_record_id", id}, {"expected_revision", revision + 2},
        {"assets", Json::array({{{"record_id", id}, {"path", "reports/document.pdf"}},
                               {{"record_id", image}, {"path", "images/plot.png"}}})}}).is_object());
    project().refresh(); ASSERT_NO_FATAL_FAILURE(settle_project());
    const auto record = call("project.reports.get", {{"handle", handle}, {"report_id", pdf_report_id}});
    ASSERT_TRUE(record.is_object()); pdf_sha = record.at("report").at("source_sha256").get<std::string>();
    ASSERT_NO_FATAL_FAILURE(load(pdf_report_id));
  }
  void hold(const std::string &operation)
  {
    ASSERT_NO_FATAL_FAILURE(load());
  ASSERT_NO_FATAL_FAILURE(mode(operation));
    ASSERT_TRUE(reports->prepare_preview());
    ASSERT_TRUE(loop.pump_until([&] { reports->sync(); return fs::exists(dir.path() / "mode.held"); }, 30));
    ASSERT_TRUE(reports->preview_busy()); ASSERT_FALSE(reports->prepared_preview());
  }
  void drain(bridge::Client &sender)
  {
    release();
    ASSERT_TRUE(bridge::test::wait_until([&] { return fs::exists(dir.path() / "mode.sent"); }, 15));
    ASSERT_TRUE(call_on(sender, "project.list", Json::object()).is_object());
    loop.run_ready(); reports->sync();
  }
  void expect_viewer()
  {
    EXPECT_EQ(store().viewer().base_payload(), shown);
    EXPECT_EQ(store().viewer().payload_serial(), payload_serial);
    EXPECT_EQ(store().viewer().camera_serial(), camera_serial);
    EXPECT_TRUE(store().viewer().save_workspace_state() == viewer_state)
        << "Report preparation changed the frozen Viewer workspace";
    EXPECT_EQ(store().viewer().evaluations_started(), 0u);
    EXPECT_TRUE(store().scripts().history().empty());
  }
  void SetUp() override
  {
    python = STK_BRIDGE_TEST_PYTHON_DEFAULT;
    if (const char *value = std::getenv("STK_BRIDGE_TEST_PYTHON"); value && *value) { python = value; }
    if (python.empty()) { python = bridge::find_executable("python3").value_or(""); }
    if (python.empty()) { GTEST_SKIP() << "Set STK_BRIDGE_TEST_PYTHON"; }
    { std::ofstream script(dir.path() / "bridge.py", std::ios::binary); script << kPreviewBridge; ASSERT_TRUE(script.good()); }
    ASSERT_TRUE(start_client("first"));
    ASSERT_TRUE(project().create(dir.str() + "/project", "Preview reports"));
  ASSERT_NO_FATAL_FAILURE(settle_project());
    project_id = project().project()->id; const auto handle = project().project()->handle;
    ASSERT_TRUE(wmtest::write_text(dir.str() + "/project/report.md", markdown));
    ASSERT_TRUE(wmtest::write_text(dir.str() + "/project/secondary.html", "<script>unsafe-secondary</script>"));
    io::Image image(2, 1); image.pixels = {255, 0, 0, 255, 0, 255, 0, 255}; png = io::encode_png(image);
    image.pixels = {0, 0, 255, 255, 255, 255, 0, 255}; second_png = io::encode_png(image);
    for (const auto &[name, bytes] : std::vector<std::pair<std::string, std::vector<uint8_t>>>{{"plot.png", png}, {"second.png", second_png}}) {
      std::ofstream output(dir.path() / "project" / name, std::ios::binary);
      output.write(reinterpret_cast<const char *>(bytes.data()), std::streamsize(bytes.size())); ASSERT_TRUE(output.good());
    }
    const auto indexed = call("project.files.index", {{"handle", handle}, {"expected_revision", 0},
        {"paths", Json::array({"report.md", "plot.png", "second.png", "secondary.html"})}});
    ASSERT_TRUE(indexed.is_object()); const auto ids = indexed.at("record_ids");
    const auto snapshot = call("project.snapshots.capture", {{"handle", handle}, {"record_ids", ids}, {"expected_revision", 1}});
    ASSERT_TRUE(snapshot.is_object());
    const auto first = call("project.reports.create", {{"handle", handle}, {"name", "Raster report"},
        {"snapshot_id", snapshot.at("snapshot").at("id")}, {"entry_record_id", ids.at(0)},
        {"assets", Json::array({{{"record_id", ids.at(0)}, {"path", "reports/report.md"}},
                               {{"record_id", ids.at(1)}, {"path", "images/plot.png"}},
                               {{"record_id", ids.at(2)}, {"path", "images/second.png"}},
                               {{"record_id", ids.at(3)}, {"path", "reports/secondary.html"}}})},
        {"report_id", report_id}, {"expected_revision", 2}});
    ASSERT_TRUE(first.is_object());
    ASSERT_TRUE(call("project.reports.create", {{"handle", handle}, {"name", "Entry only"},
        {"snapshot_id", snapshot.at("snapshot").at("id")}, {"entry_record_id", ids.at(0)},
        {"assets", Json::array({{{"record_id", ids.at(0)}, {"path", "reports/report.md"}}})},
        {"report_id", text_report_id}, {"expected_revision", 3}}).is_object());
    project().refresh();
  ASSERT_NO_FATAL_FAILURE(settle_project()); ASSERT_EQ(project().project()->revision, 4);
    const auto saved = call("project.reports.get", {{"handle", handle}, {"report_id", report_id}});
    ASSERT_TRUE(saved.is_object()); manifest = saved.at("report").at("manifest");
    source_sha = saved.at("report").at("source_sha256").get<std::string>();
    reports = std::make_unique<ProjectReports>(store()); ASSERT_TRUE(reports->supported());
    store().viewer().set_auto_evaluate(false); store().viewer().prefetch_neighbours = false;
    shown = std::make_shared<io::Payload>(io::read_stkp(std::string(STK_REPO_ROOT) + "/desktop/tests/viewer/fixtures/muferro_domains.stkp"));
    store().viewer().open_payload(shown, "Existing result");
    // Let normal, read-only catalog loading finish before recording the preserved Viewer.
    store().viewer().refresh_metadata();
    ASSERT_TRUE(loop.pump_until([&] {
      return store().viewer().presets_loaded() && !store().viewer().catalog().is_null() &&
             store().viewer().colormaps();
    }, 30)) << store().viewer().metadata_error();
    viewer_state = store().viewer().save_workspace_state();
    camera_serial = store().viewer().camera_serial(); payload_serial = store().viewer().payload_serial();
  }
  void TearDown() override
  {
    release(); if (shown) { expect_viewer(); }
    reports.reset(); project().attach(nullptr); store().set_bridge(nullptr);
    if (client) { client->close(); EXPECT_EQ(client->stats().schema_violations, 0u); }
    loop.run_ready();
  }
};

TEST_F(ReportsPreviewPython, PublishesCompleteVerifiedCollectionWithoutChangingTheSourceReader)
{
  ASSERT_NO_FATAL_FAILURE(load());
  ASSERT_TRUE(reports->select_asset("images/second.png")); ASSERT_TRUE(reports->read_asset());
  ASSERT_NO_FATAL_FAILURE(settle());
  const auto read_version = reports->asset_version(); const auto selected = reports->selected();
  const auto history = call("project.history", {{"handle", reports->handle()}});
  for (const char *name : {"report.md", "plot.png", "second.png", "secondary.html"}) { ASSERT_TRUE(fs::remove(dir.path() / "project" / name)); }
  ASSERT_TRUE(reports->prepare_preview()); EXPECT_FALSE(reports->prepared_preview());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->prepared_preview()) << reports->preview_error();
  const auto &ready = *reports->prepared_preview();
  EXPECT_EQ(ready.identity.project_id, project_id); EXPECT_EQ(ready.identity.report_id, report_id);
  EXPECT_EQ(ready.identity.source_sha256, source_sha); EXPECT_EQ(ready.entry_path, "reports/report.md");
  ASSERT_EQ(ready.assets.size(), 3u);
  EXPECT_EQ(ready.assets[0].path, ready.entry_path); EXPECT_EQ(ready.assets[0].mime, "text/html; charset=utf-8");
  const std::string html(ready.assets[0].bytes.begin(), ready.assets[0].bytes.end());
  EXPECT_NE(html.find("<h1>Frozen report</h1>"), std::string::npos); EXPECT_EQ(html.find("secondary.html"), std::string::npos);
  EXPECT_NE(html.find(ready.identity.session_id + "/" + project_id + "/" + report_id + "/" + source_sha + "/assets/"), std::string::npos);
  EXPECT_NE(core::Sha256::hex(ready.assets[0].bytes), manifest.at("assets")[0].at("sha256").get<std::string>());
  EXPECT_EQ(ready.assets[1].path, "images/plot.png"); EXPECT_EQ(ready.assets[1].bytes, png);
  EXPECT_EQ(ready.assets[2].path, "images/second.png"); EXPECT_EQ(ready.assets[2].bytes, second_png);
  EXPECT_EQ(reports->asset_path(), "images/second.png"); EXPECT_EQ(reports->asset_bytes(), second_png);
  EXPECT_EQ(reports->asset_version(), read_version); EXPECT_EQ(reports->selected(), selected);
  EXPECT_EQ(call("project.history", {{"handle", reports->handle()}}), history);
  const auto session = ready.identity.session_id;
  const auto version = reports->preview_version();
  reports->clear_preview(); EXPECT_FALSE(reports->prepared_preview()); EXPECT_GT(reports->preview_version(), version);
  EXPECT_EQ(reports->asset_bytes(), second_png);
  ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_TRUE(reports->prepared_preview());
  EXPECT_NE(reports->prepared_preview()->identity.session_id, session);
}

TEST_F(ReportsPreviewPython, ImageReadsAreSerialAndNoPartialCollectionIsExposed)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_image"));
  EXPECT_EQ(count("prepare"), 1); EXPECT_EQ(count("asset:images/plot.png"), 1); EXPECT_EQ(count("asset:images/second.png"), 0);
  ASSERT_FALSE(reports->prepared_preview()); ASSERT_TRUE(reports->preview_busy());
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->prepared_preview()) << reports->preview_error();
  EXPECT_EQ(count("asset:images/second.png"), 1); EXPECT_EQ(reports->prepared_preview()->assets.size(), 3u);
}

TEST_F(ReportsPreviewPython, EntryWithoutImagesPublishesOneSanitizedAsset)
{
  ASSERT_NO_FATAL_FAILURE(load(text_report_id)); ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->prepared_preview()) << reports->preview_error();
  EXPECT_EQ(reports->prepared_preview()->assets.size(), 1u);
  EXPECT_EQ(count("asset:images/plot.png"), 0); EXPECT_EQ(count("asset:images/second.png"), 0);
}

TEST_F(ReportsPreviewPython, TakingTheCollectionMovesBytesAndLeavesTheRawReaderUntouched)
{
  ASSERT_NO_FATAL_FAILURE(load()); ASSERT_TRUE(reports->read_asset());
  ASSERT_NO_FATAL_FAILURE(settle());
  const auto raw = reports->asset_bytes(); const auto read_version = reports->asset_version();
  ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->prepared_preview());
  const auto *entry_data = reports->prepared_preview()->assets[0].bytes.data();
  auto prepared = reports->take_prepared_preview();
  ASSERT_TRUE(prepared); EXPECT_EQ(prepared->assets[0].bytes.data(), entry_data);
  EXPECT_EQ(prepared->project_scope_epoch, store().project_scope_epoch());
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->take_prepared_preview());
  EXPECT_EQ(reports->asset_bytes(), raw); EXPECT_EQ(reports->asset_version(), read_version);
}

TEST_F(ReportsPreviewPython, ScopeInvalidationClearsReadyPreviewWithoutPollingOrDiscardingRawBytes)
{
  ASSERT_NO_FATAL_FAILURE(load()); ASSERT_TRUE(reports->read_asset());
  ASSERT_NO_FATAL_FAILURE(settle());
  const auto raw = reports->asset_bytes(); const auto selected = reports->selected();
  const auto raw_version = reports->asset_version();
  ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_TRUE(reports->prepared_preview());
  store().invalidate_project_scope();
  // Do not sync, draw or pump: resource revocation is synchronous.
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_busy());
  EXPECT_EQ(reports->asset_bytes(), raw); EXPECT_EQ(reports->asset_version(), raw_version);
  EXPECT_EQ(reports->selected(), selected); EXPECT_EQ(count("prepare"), 1);
}

TEST_F(ReportsPreviewPython, ChangedEventRevokesPreviewBeforeTheNewCatalogCanBeRead)
{
  ASSERT_NO_FATAL_FAILURE(load()); ASSERT_TRUE(reports->read_asset());
  ASSERT_NO_FATAL_FAILURE(settle());
  const auto raw = reports->asset_bytes(); const auto raw_version = reports->asset_version();
  ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_TRUE(reports->prepared_preview());
  ASSERT_NO_FATAL_FAILURE(mode("hold_catalog"));
  ASSERT_TRUE(call("project.apply", {{"handle", reports->handle()}, {"expected_revision", 4},
      {"commands", Json::array({{{"op", "create_table"}, {"id", "f6666666-6666-4666-8666-666666666666"}, {"name", "Changed"}}})}}).is_object());
  ASSERT_TRUE(loop.pump_until([&] { return fs::exists(dir.path() / "mode.held"); }, 30));
  ASSERT_TRUE(project().project()); EXPECT_EQ(project().project()->revision, 4);
  EXPECT_TRUE(project().busy());
  // The cached revision is still old and ProjectReports::sync was never called.
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_EQ(reports->revision(), 4);
  EXPECT_EQ(reports->asset_bytes(), raw); EXPECT_EQ(reports->asset_version(), raw_version);
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_EQ(reports->revision(), 5); EXPECT_EQ(count("prepare"), 1);
}

TEST_F(ReportsPreviewPython, ReplacingTheBridgeRevokesReadyPreviewBeforeProjectSync)
{
  ASSERT_NO_FATAL_FAILURE(load()); ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->prepared_preview());
  store().set_bridge(nullptr);
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_busy());
  store().set_bridge(client.get());
}

TEST_F(ReportsPreviewPython, ChangingTheLocalReportClosesItsNativeOwnerBeforeDiscardingBytes)
{
  ASSERT_NO_FATAL_FAILURE(load()); ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->prepared_preview());
  int closed = 0;
  reports->on_preview_invalidated = [&] {
    ++closed;
    // This is the last instant at which the old collection may back a native view.
    EXPECT_TRUE(reports->prepared_preview());
    EXPECT_EQ(reports->selected().at("id"), report_id);
  };
  const bool accepted = reports->load(text_report_id);
  reports->on_preview_invalidated = nullptr;
  ASSERT_TRUE(accepted); EXPECT_EQ(closed, 1);
  EXPECT_FALSE(reports->prepared_preview());
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_EQ(reports->selected().at("id"), text_report_id);
}

class ReportsPreviewInvalid : public ReportsPreviewPython, public ::testing::WithParamInterface<const char *> {};
TEST_P(ReportsPreviewInvalid, RejectsAValidWireShapeThatDoesNotMatchFrozenContent)
{
  ASSERT_NO_FATAL_FAILURE(load());
  ASSERT_NO_FATAL_FAILURE(mode(GetParam()));
  ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_error().empty()); EXPECT_FALSE(reports->preview_busy());
  EXPECT_FALSE(reports->asset_loaded()); EXPECT_EQ(reports->asset_path(), "reports/report.md");
  ASSERT_NO_FATAL_FAILURE(mode("")); reports->sync();
  EXPECT_EQ(count("prepare"), 1); // No automatic retry after a bad receipt.
}
INSTANTIATE_TEST_SUITE_P(Receipts, ReportsPreviewInvalid, ::testing::Values(
    "source_hash", "render_bytes", "noncanonical", "project", "resource_hash", "omitted", "reordered", "total",
    "image_bytes", "image_second_bytes", "image_identity"));

TEST_F(ReportsPreviewPython, ClearPreviewInvalidatesHeldEntryWithoutChangingReportSelection)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_prepare")); const auto selected = reports->selected();
  reports->clear_preview();
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_busy()); EXPECT_TRUE(reports->preview_error().empty());
  EXPECT_EQ(reports->selected(), selected); EXPECT_EQ(count("asset:images/plot.png"), 0);
}

TEST_F(ReportsPreviewPython, FullClearDropsEveryPendingByteBeforeTheFinalReply)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_second"));
  reports->clear();
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_busy());
  EXPECT_TRUE(reports->selected().is_null()); EXPECT_TRUE(reports->preview_error().empty());
}

TEST_F(ReportsPreviewPython, ClosingProjectInvalidatesTheFinalImageReply)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_second")); ASSERT_TRUE(project().close());
  EXPECT_FALSE(reports->preview_busy()); EXPECT_FALSE(reports->prepared_preview());
  ASSERT_TRUE(loop.pump_until([&] { reports->sync(); return !project().loaded() && !project().busy(); }, 30));
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_busy());
  EXPECT_TRUE(reports->handle().empty()); EXPECT_TRUE(reports->selected().is_null());
}

TEST_F(ReportsPreviewPython, SwitchingReportsInvalidatesAnAlreadyReadButHeldImage)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_image"));
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(load(text_report_id));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  EXPECT_EQ(reports->selected().at("id"), text_report_id); EXPECT_FALSE(reports->prepared_preview());
  EXPECT_EQ(count("asset:images/second.png"), 0);
}

TEST_F(ReportsPreviewPython, ProjectSwitchInvalidatesThePreviousOpenedHandle)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_image")); const auto old = reports->handle();
  ASSERT_TRUE(project().create(dir.str() + "/other", "Other"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  ASSERT_NE(reports->handle(), old);
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  EXPECT_TRUE(reports->selected().is_null()); EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_busy());
  EXPECT_EQ(count("asset:images/second.png"), 0);
}

TEST_F(ReportsPreviewPython, RevisionChangeDiscardsHeldImageAndCannotPublishOldCollection)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_second"));
  ASSERT_TRUE(call("project.apply", {{"handle", reports->handle()}, {"expected_revision", 4},
      {"commands", Json::array({{{"op", "create_table"}, {"id", "e5555555-5555-4555-8555-555555555555"}, {"name", "Changed"}}})}}).is_object());
  project().refresh();
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain(*client));
  EXPECT_EQ(reports->revision(), 5); EXPECT_FALSE(reports->prepared_preview()); EXPECT_TRUE(reports->selected().is_null());
  EXPECT_EQ(count("asset:images/second.png"), 1);
}

TEST_F(ReportsPreviewPython, NewBridgeRejectsTheOldSessionsHeldResponse)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_second")); const auto old_handle = reports->handle();
  auto old = std::move(client); project().attach(nullptr); store().set_bridge(nullptr); reports->sync();
  ASSERT_NO_FATAL_FAILURE(mode("")); ASSERT_TRUE(start_client("second"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  ASSERT_NE(reports->handle(), old_handle);
  ASSERT_NO_FATAL_FAILURE(drain(*old));
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_TRUE(reports->selected().is_null()); EXPECT_EQ(count("asset:images/plot.png"), 1);
  old->close(); EXPECT_EQ(old->stats().schema_violations, 0u);
}

TEST_F(ReportsPreviewPython, RestartOfTheSameClientInvalidatesPidSpawnedScopeWithoutRetry)
{
  ASSERT_NO_FATAL_FAILURE(hold("hold_prepare")); const auto spawned = client->stats().spawned;
  ASSERT_NO_FATAL_FAILURE(mode(""));
  // restart() only resumes a Failed/Stopped client. Crash this fixture's held process to
  // exercise a real new generation of the same live Client instead of a no-op restart call.
  { std::ofstream crash(dir.path() / "mode.crash"); crash << "terminate held fixture"; ASSERT_TRUE(crash.good()); }
  ASSERT_TRUE(loop.pump_until([&] {
    reports->sync(); return client->stats().spawned > spawned && client->state() == bridge::BridgeState::Ready;
  }, 60));
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_busy()); EXPECT_TRUE(reports->selected().is_null());
  EXPECT_EQ(count("prepare"), 1); EXPECT_EQ(count("asset:images/plot.png"), 0);
}

TEST_F(ReportsPreviewPython, LegacyBridgeKeepsSourceReadingButExplicitlyRejectsResourcePreview)
{
  auto old = std::move(client); project().attach(nullptr); store().set_bridge(nullptr); reports->sync();
  ASSERT_NO_FATAL_FAILURE(mode("old_bridge")); ASSERT_TRUE(start_client("legacy"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  EXPECT_TRUE(reports->supported()); EXPECT_FALSE(reports->supports("project.reports.preview_resources"));
  ASSERT_NO_FATAL_FAILURE(load()); EXPECT_FALSE(reports->prepare_preview()); EXPECT_FALSE(reports->preview_error().empty());
  ASSERT_TRUE(reports->read_asset());
  ASSERT_NO_FATAL_FAILURE(settle());
  EXPECT_TRUE(reports->asset_loaded()); EXPECT_EQ(std::string(reports->asset_bytes().begin(), reports->asset_bytes().end()), markdown);
  EXPECT_EQ(count("prepare"), 0); old->close(); EXPECT_EQ(old->stats().schema_violations, 0u);
}

TEST_F(ReportsPreviewPython, RestoringAReportWorkspaceDoesNotAutomaticallyPrepareOrReadBytes)
{
  auto &area = f.area("a4"); ASSERT_TRUE(area.set_tabs({kEditorReports, kEditorPython}, 0));
  const nlohmann::json state = {{"version", 1}, {"project_id", project_id}, {"report_id", report_id},
                      {"source_sha256", source_sha}, {"asset_path", "images/second.png"}, {"text_page", 0}};
  ASSERT_TRUE(area.editor().load_workspace_state(state));
  ASSERT_TRUE(loop.pump_until([&] {
    f.screen.run_deferred(); f.drv->frame();
    const auto *read = f.screen.ui()->find("reports_read_asset"); return read && read->enabled;
  }, 30));
  EXPECT_EQ(area.editor().save_workspace_state(), state);
  EXPECT_EQ(count("prepare"), 0); EXPECT_EQ(count("asset:images/second.png"), 0);
  EXPECT_FALSE(reports->prepared_preview());
}
TEST_F(ReportsPreviewPython, PdfUsesOneIdentityResponseWithBinaryBytesAndFreshSessions)
{
  ASSERT_NO_FATAL_FAILURE(create_pdf()); ASSERT_TRUE(reports->supports_preview());
  ASSERT_TRUE(reports->read_asset()); ASSERT_NO_FATAL_FAILURE(settle());
  const auto raw = reports->asset_bytes(); const auto version = reports->asset_version();
  const auto selection = reports->selected();
  ASSERT_TRUE(fs::remove(dir.path() / "project/document.pdf"));
  ASSERT_TRUE(fs::remove(dir.path() / "project/plot.png"));
  std::string previous;
  for (int i = 0; i < 2; ++i) {
    ASSERT_TRUE(reports->prepare_preview()); ASSERT_FALSE(reports->prepared_preview());
    ASSERT_NO_FATAL_FAILURE(settle());
    auto prepared = reports->take_prepared_preview(); ASSERT_TRUE(prepared) << reports->preview_error();
    EXPECT_EQ(prepared->identity.project_id, project_id); EXPECT_EQ(prepared->identity.report_id, pdf_report_id);
    EXPECT_EQ(prepared->identity.source_sha256, pdf_sha); EXPECT_NE(prepared->identity.session_id, previous);
    previous = prepared->identity.session_id;
    EXPECT_EQ(prepared->project_scope_epoch, store().project_scope_epoch());
    ASSERT_EQ(prepared->assets.size(), 1u); EXPECT_EQ(prepared->entry_path, "reports/document.pdf");
    EXPECT_EQ(prepared->assets[0].mime, "application/pdf"); EXPECT_EQ(prepared->assets[0].bytes, pdf_bytes);
    EXPECT_EQ(reports->selected(), selection); EXPECT_EQ(reports->asset_bytes(), raw); EXPECT_EQ(reports->asset_version(), version);
  }
  EXPECT_EQ(count("pdf_prepare"), 2); EXPECT_EQ(count("prepare"), 0);
  EXPECT_EQ(count("asset:reports/document.pdf"), 1); EXPECT_EQ(count("asset:images/plot.png"), 0);
}

TEST_F(ReportsPreviewPython, PdfAcceptsTheFullFourMiBBudgetWithoutTheHtmlInputLimit)
{
  ASSERT_NO_FATAL_FAILURE(create_pdf(4 * 1024 * 1024));
  ASSERT_TRUE(reports->supports_preview()); ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_TRUE(reports->prepared_preview()) << reports->preview_error();
  ASSERT_EQ(reports->prepared_preview()->assets.size(), 1u);
  EXPECT_EQ(reports->prepared_preview()->assets[0].bytes, pdf_bytes);
}

TEST_F(ReportsPreviewPython, PdfWorksWithLegacyPreviewWhileHtmlStillRequiresResourcePreparation)
{
  ASSERT_NO_FATAL_FAILURE(create_pdf());
  auto old = std::move(client); project().attach(nullptr); store().set_bridge(nullptr); reports->sync();
  ASSERT_NO_FATAL_FAILURE(mode("old_bridge")); ASSERT_TRUE(start_client("legacy-pdf"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  ASSERT_NO_FATAL_FAILURE(load(pdf_report_id));
  ASSERT_FALSE(reports->supports("project.reports.preview_resources")); ASSERT_TRUE(reports->supports_preview());
  ASSERT_TRUE(reports->prepare_preview()); ASSERT_NO_FATAL_FAILURE(settle());
  ASSERT_TRUE(reports->prepared_preview()); EXPECT_EQ(reports->prepared_preview()->assets[0].bytes, pdf_bytes);
  ASSERT_NO_FATAL_FAILURE(load()); EXPECT_FALSE(reports->supports_preview()); EXPECT_FALSE(reports->prepare_preview());
  EXPECT_EQ(count("pdf_prepare"), 1); EXPECT_EQ(count("prepare"), 0); old->close();
}

TEST_F(ReportsPreviewPython, MissingIdentityPreviewDisablesPdfWithoutDisablingHtml)
{
  ASSERT_NO_FATAL_FAILURE(create_pdf());
  auto old = std::move(client); project().attach(nullptr); store().set_bridge(nullptr); reports->sync();
  ASSERT_NO_FATAL_FAILURE(mode("no_identity_preview")); ASSERT_TRUE(start_client("no-pdf"));
  ASSERT_NO_FATAL_FAILURE(settle_project()); reports->sync();
  ASSERT_NO_FATAL_FAILURE(load(pdf_report_id));
  EXPECT_FALSE(reports->supports_preview()); EXPECT_FALSE(reports->prepare_preview());
  EXPECT_FALSE(reports->preview_error().empty()); EXPECT_EQ(count("pdf_prepare"), 0);
  ASSERT_NO_FATAL_FAILURE(load()); ASSERT_TRUE(reports->supports_preview());
  ASSERT_TRUE(reports->prepare_preview()); ASSERT_NO_FATAL_FAILURE(settle()); ASSERT_TRUE(reports->prepared_preview());
  old->close();
}

class ReportsPdfInvalid : public ReportsPreviewPython, public ::testing::WithParamInterface<const char *> {};
TEST_P(ReportsPdfInvalid, RejectsValidWireReceiptsBeforePublishingAnyPdfBytes)
{
  ASSERT_NO_FATAL_FAILURE(create_pdf()); const auto selected = reports->selected();
  ASSERT_NO_FATAL_FAILURE(mode(GetParam())); ASSERT_TRUE(reports->prepare_preview());
  ASSERT_NO_FATAL_FAILURE(settle()); EXPECT_FALSE(reports->prepared_preview());
  EXPECT_FALSE(reports->preview_error().empty()); EXPECT_FALSE(reports->preview_busy());
  EXPECT_EQ(reports->selected(), selected); EXPECT_FALSE(reports->asset_loaded());
  EXPECT_EQ(count("pdf_prepare"), 1); EXPECT_EQ(count("asset:images/plot.png"), 0);
  ASSERT_NO_FATAL_FAILURE(mode("")); reports->sync(); EXPECT_EQ(count("pdf_prepare"), 1);
}
INSTANTIATE_TEST_SUITE_P(Receipts, ReportsPdfInvalid, ::testing::Values(
    "pdf_project", "pdf_report", "pdf_manifest", "pdf_revision", "pdf_path", "pdf_mime",
    "pdf_source_mime", "pdf_renderer", "pdf_source_hash", "pdf_display_hash", "pdf_size",
    "pdf_source_size", "pdf_bytes", "pdf_noncanonical"));

class ReportsPdfInvalidation : public ReportsPreviewPython, public ::testing::WithParamInterface<const char *> {};
TEST_P(ReportsPdfInvalidation, HeldPdfCannotEscapeAnInvalidatedScopeOrSelection)
{
  ASSERT_NO_FATAL_FAILURE(create_pdf());
  ASSERT_NO_FATAL_FAILURE(mode("hold_pdf"));
  ASSERT_TRUE(reports->prepare_preview());
  ASSERT_TRUE(loop.pump_until([&] { reports->sync(); return fs::exists(dir.path() / "mode.held"); }, 30));
  EXPECT_FALSE(reports->prepared_preview()); std::unique_ptr<bridge::Client> old;
  const std::string operation = GetParam();
  if (operation == "clear") { reports->clear_preview(); }
  else if (operation == "scope") { store().invalidate_project_scope(); }
  else if (operation == "report") { ASSERT_NO_FATAL_FAILURE(load()); }
  else if (operation == "close") { ASSERT_TRUE(project().close()); }
  else if (operation == "revision") {
    ASSERT_TRUE(call("project.apply", {{"handle", project().project()->handle}, {"expected_revision", reports->revision()},
        {"commands", Json::array({{{"op", "create_table"}, {"id", "f6666666-6666-4666-8666-666666666666"}, {"name", "Later"}}})}}).is_object());
    project().refresh(); ASSERT_NO_FATAL_FAILURE(settle_project());
  }
  else if (operation == "project") {
    ASSERT_TRUE(project().create(dir.str() + "/other-pdf", "Other")); ASSERT_NO_FATAL_FAILURE(settle_project());
  }
  else if (operation == "bridge") {
    old = std::move(client); project().attach(nullptr); store().set_bridge(nullptr); reports->sync();
    ASSERT_TRUE(start_client("replacement-pdf")); ASSERT_NO_FATAL_FAILURE(settle_project());
  }
  ASSERT_NO_FATAL_FAILURE(mode(""));
  ASSERT_NO_FATAL_FAILURE(drain(old ? *old : *client));
  EXPECT_FALSE(reports->prepared_preview()); EXPECT_FALSE(reports->preview_busy()); EXPECT_EQ(count("pdf_prepare"), 1);
  if (old) { old->close(); }
}
INSTANTIATE_TEST_SUITE_P(Scopes, ReportsPdfInvalidation,
    ::testing::Values("clear", "scope", "report", "close", "revision", "project", "bridge"));
}  // namespace
}  // namespace stk::app

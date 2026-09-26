/* SPDX-License-Identifier: GPL-2.0-or-later */
/** \file Wire-level units of stk_bridge: framing, strict decoding, errors, schema, types. */

#include <gtest/gtest.h>

#include <cmath>

#include "stk/bridge/future.hh"
#include "stk/bridge/log_ring.hh"
#include "stk/bridge/protocol.hh"
#include "stk/bridge/python.hh"
#include "stk/bridge/schema.hh"
#include "stk/bridge/types.hh"

namespace stk::bridge {
namespace {

std::vector<std::string> split_all(LineSplitter &splitter, const std::vector<std::string> &pieces,
                                   std::vector<size_t> *oversize = nullptr)
{
  std::vector<std::string> lines;
  for (const std::string &piece : pieces) {
    splitter.feed(
        piece, [&](std::string_view line) { lines.emplace_back(line); },
        [&](size_t n) {
          if (oversize) {
            oversize->push_back(n);
          }
        });
  }
  return lines;
}

TEST(Framing, SplitsLinesAcrossArbitraryReads)
{
  const std::string stream = "{\"a\":1}\n{\"b\":\"中文🧲\"}\n\n{\"c\":3}\n";
  for (size_t step = 1; step <= stream.size(); step++) {
    LineSplitter splitter(1024);
    std::vector<std::string> pieces;
    for (size_t i = 0; i < stream.size(); i += step) {
      pieces.push_back(stream.substr(i, step));
    }
    const auto lines = split_all(splitter, pieces);
    ASSERT_EQ(lines.size(), 4u) << "step " << step;
    EXPECT_EQ(lines[1], "{\"b\":\"中文🧲\"}");
    EXPECT_EQ(lines[2], "");
    EXPECT_EQ(splitter.pending(), 0u);
  }
}

TEST(Framing, DiscardsOversizedLinesAndKeepsGoing)
{
  LineSplitter splitter(10);
  std::vector<size_t> oversize;
  const auto lines = split_all(splitter, {"0123456789\n", "01234", "567890123", "45\nok\n", "x"}, &oversize);
  ASSERT_EQ(lines.size(), 2u);
  EXPECT_EQ(lines[0], "0123456789"); /* exactly the limit is fine */
  EXPECT_EQ(lines[1], "ok");
  ASSERT_EQ(oversize.size(), 1u);
  EXPECT_EQ(oversize[0], 16u);
  EXPECT_EQ(splitter.pending(), 1u); /* "x": an unterminated line is never delivered */
}

TEST(Decode, AcceptsStrictObjectsAndDropsCarriageReturn)
{
  const Json message = decode_line("{\"id\":7,\"result\":{\"t\":\"计算\"}}\r");
  EXPECT_EQ(message["id"], 7);
  EXPECT_EQ(message["result"]["t"], "计算");
}

TEST(Decode, RejectsInvalidUtf8DuplicatesNonFiniteAndNonObjects)
{
  EXPECT_THROW(decode_line("{\"t\":\"\xff\"}"), ProtocolError);
  EXPECT_THROW(decode_line("{\"t\":\"\xe8\xae\"}"), ProtocolError); /* truncated character */
  EXPECT_THROW(decode_line("{\"a\":1,\"a\":2}"), ProtocolError);
  EXPECT_THROW(decode_line("{\"x\":{\"a\":1,\"b\":{\"a\":1},\"a\":3}}"), ProtocolError);
  EXPECT_NO_THROW(decode_line("{\"x\":{\"a\":1},\"y\":{\"a\":1}}")); /* same key in sibling objects */
  EXPECT_THROW(decode_line("{\"v\":NaN}"), ProtocolError);
  EXPECT_THROW(decode_line("{\"v\":Infinity}"), ProtocolError);
  EXPECT_THROW(decode_line("[1]"), ProtocolError);
  EXPECT_THROW(decode_line("{broken"), ProtocolError);
}

TEST(Encode, IsStrictCompactUtf8)
{
  Json message = {{"id", 1}, {"method", "echo"}, {"params", {{"t", "中文 🧲"}}}};
  const std::string line = encode_line(message);
  EXPECT_EQ(line.back(), '\n');
  EXPECT_NE(line.find("中文 🧲"), std::string::npos); /* not \u-escaped */
  EXPECT_EQ(line.find('\n'), line.size() - 1);
  message["params"]["v"] = std::nan("");
  EXPECT_THROW(encode_line(message), ProtocolError);
  Json bad = {{"t", std::string("\xff")}};
  EXPECT_THROW(encode_line(bad), ProtocolError);
}

TEST(Classify, EnvelopesOfSection3)
{
  EXPECT_EQ(classify_message(Json{{"id", 1}, {"result", Json::object()}}), MessageKind::Response);
  EXPECT_EQ(classify_message(Json{{"id", "abc"}, {"error", {{"code", "busy"}}}}), MessageKind::Response);
  EXPECT_EQ(classify_message(Json{{"id", nullptr}, {"error", {{"code", "parse_error"}}}}), MessageKind::Response);
  EXPECT_EQ(classify_message(Json{{"event", "logs.chunk"}, {"data", Json::object()}}), MessageKind::Event);
  std::string why;
  EXPECT_EQ(classify_message(Json{{"id", nullptr}, {"result", Json::object()}}, &why), MessageKind::Invalid);
  EXPECT_EQ(classify_message(Json{{"id", 1}, {"result", Json::object()}, {"error", Json::object()}}),
            MessageKind::Invalid);
  EXPECT_EQ(classify_message(Json{{"id", 1}, {"result", 3}}), MessageKind::Invalid);
  EXPECT_EQ(classify_message(Json{{"id", -1}, {"result", Json::object()}}), MessageKind::Invalid);
  EXPECT_EQ(classify_message(Json{{"event", "x"}, {"data", 1}}), MessageKind::Invalid);
  EXPECT_EQ(classify_message(Json{{"event", "x"}, {"data", Json::object()}, {"extra", 1}}), MessageKind::Invalid);
  EXPECT_EQ(classify_message(Json{{"hello", 1}}), MessageKind::Invalid);
}

TEST(Errors, AllTwentyCodesRoundTripWithTheirRetryDefault)
{
  const std::vector<std::pair<const char *, bool>> codes = {
      {"parse_error", false},  {"line_too_long", false},   {"invalid_request", false},
      {"unknown_method", false}, {"invalid_params", false}, {"unsupported", false},
      {"not_found", false},    {"unauthorized", false},    {"unavailable", true},
      {"conflict", false},     {"review_not_inspected", false}, {"remote_error", false},
      {"checksum_mismatch", true}, {"graph_error", false}, {"cancelled", false},
      {"timeout", true},       {"busy", true},             {"result_too_large", false},
      {"shutting_down", false}, {"internal_error", false},
  };
  for (const auto &[name, retryable] : codes) {
    const ErrorCode code = error_code_from_name(name);
    EXPECT_NE(code, ErrorCode::Unknown) << name;
    EXPECT_EQ(error_code_name(code), name);
    EXPECT_EQ(error_code_retryable(code), retryable) << name;
  }
  EXPECT_EQ(error_code_from_name("brand_new"), ErrorCode::Unknown);
  const Error error = Error::from_json(
      {{"code", "remote_error"}, {"message", "HTTP 503"}, {"retryable", true}, {"data", {{"action", 1}}}});
  EXPECT_EQ(error.code, ErrorCode::RemoteError);
  EXPECT_TRUE(error.retryable); /* the bridge's flag wins over the table (remote 5xx) */
  EXPECT_EQ(error.data["action"], 1);
  EXPECT_FALSE(error.local);
  const Error unknown = Error::from_json({{"code", "brand_new"}, {"message", "m"}, {"retryable", false}});
  EXPECT_EQ(unknown.code, ErrorCode::Unknown);
  EXPECT_EQ(unknown.name, "brand_new");
  EXPECT_EQ(Error::from_json(unknown.to_json()).name, "brand_new");
}

TEST(Retry, ReadsAndKeyedCreatesOnly)
{
  for (const char *method : {"hello", "connections.list", "task.get", "task.list", "graph.presets", "probe",
                             "colormaps.list", "hub.policy", "blob.ensure", "workspace.files"})
  {
    EXPECT_TRUE(method_is_retry_safe(method, Json::object())) << method;
  }
  EXPECT_TRUE(method_is_retry_safe("task.submit", Json{{"idempotency_key", "k"}}));
  EXPECT_TRUE(method_is_retry_safe("workspace.create", Json{{"idempotency_key", "k"}}));
  EXPECT_FALSE(method_is_retry_safe("workspace.create", Json{{"name", "n"}}));
  EXPECT_TRUE(method_is_retry_safe("task.cancel", Json{{"idempotency_key", "k"}}));
  EXPECT_FALSE(method_is_retry_safe("task.cancel", Json::object()));
  EXPECT_TRUE(method_is_retry_safe("upload.start", Json{{"idempotency_key", "k"}}));
  EXPECT_TRUE(method_is_retry_safe("download.start", Json{{"idempotency_key", "k"}}));
  EXPECT_TRUE(method_is_retry_safe("graph.evaluate", Json{{"mode", "hub"}}));
  EXPECT_FALSE(method_is_retry_safe("graph.evaluate", Json{{"mode", "local"}}));
  EXPECT_FALSE(method_is_retry_safe("graph.evaluate", Json::object()));
  for (const char *method : {"connections.add_runtime", "connections.pair_hub", "connections.remove",
                             "connections.local_start", "hub.review", "upload.start", "download.start",
                             "transfer.resume", "transfer.cancel", "graph.cancel", "shutdown", "unsubscribe",
                             "something.new"})
  {
    EXPECT_FALSE(method_is_retry_safe(method, Json::object())) << method;
  }
  EXPECT_TRUE(method_is_subscribe("logs.subscribe"));
  EXPECT_FALSE(method_is_subscribe("unsubscribe"));
}

TEST(Schema, InlinesLocalRefsLikeThePythonBridge)
{
  const Json document = {{"$defs",
                          {{"id", {{"type", "integer"}}},
                           {"wrap", {{"$ref", "#/$defs/id"}, {"minimum", 1}}},
                           {"a~b/c", {{"type", "string"}}}}},
                         {"properties", {{"x", {{"$ref", "#/$defs/wrap"}}}, {"y", {{"$ref", "#/$defs/a~0b~1c"}}}}}};
  const Json inlined = inline_schema_refs(document, document);
  EXPECT_FALSE(inlined.contains("$defs"));
  EXPECT_EQ(inlined["properties"]["x"]["allOf"][0]["type"], "integer");
  EXPECT_EQ(inlined["properties"]["x"]["allOf"][1]["minimum"], 1);
  EXPECT_EQ(inlined["properties"]["y"]["type"], "string");
  const Json cyclic = {{"$defs", {{"a", {{"$ref", "#/$defs/a"}}}}}, {"$ref", "#/$defs/a"}};
  EXPECT_THROW(inline_schema_refs(cyclic, cyclic), std::runtime_error);
  const Json remote = {{"$ref", "https://example.com/s.json"}};
  EXPECT_THROW(inline_schema_refs(remote, remote), std::runtime_error);
}

TEST(Schema, EmbeddedSchemaValidatesMessagesBothWays)
{
  const ProtocolSchema &schema = ProtocolSchema::embedded();
  const auto methods = schema.method_names();
  EXPECT_GE(methods.size(), 42u);
  for (const char *method : {"hello", "logs.subscribe", "graph.evaluate", "hub.policy", "colormaps.list"}) {
    EXPECT_TRUE(schema.has_method(method)) << method;
  }
  EXPECT_TRUE(schema.has_event("logs.chunk"));
  EXPECT_TRUE(schema.check_request({{"id", 1}, {"method", "hello"}, {"params", {{"protocol", 1}}}}).empty());
  const auto missing = schema.check_request({{"id", 1}, {"method", "task.get"}, {"params", {{"connection", "local"}}}});
  ASSERT_FALSE(missing.empty());
  EXPECT_EQ(missing[0].path.rfind("/params", 0), 0u);
  EXPECT_FALSE(schema.check_request({{"id", 1}, {"method", "hello"}, {"params", {{"protocol", 1}, {"typo", 1}}}})
                   .empty());
  EXPECT_FALSE(schema.check_request({{"id", 1}, {"method", "no.such"}}).empty());
  const Json chunk = {{"event", "logs.chunk"},
                      {"data",
                       {{"sub", std::string(32, 'a')},
                        {"stream", "stdout"},
                        {"text", "中"},
                        {"offset", 0},
                        {"next_offset", 3}}}};
  EXPECT_TRUE(schema.check_event(chunk).empty());
  Json bad_chunk = chunk;
  bad_chunk["data"]["stream"] = "stdin";
  EXPECT_FALSE(schema.check_event(bad_chunk).empty());
  EXPECT_FALSE(schema.check_event({{"event", "no.such"}, {"data", Json::object()}}).empty());
  EXPECT_TRUE(schema.check_response({{"id", 3}, {"result", {{"sub", std::string(32, 'b')}}}}, "watch").empty());
  EXPECT_FALSE(schema.check_response({{"id", 3}, {"result", {{"sub", "short"}}}}, "watch").empty());
  EXPECT_TRUE(schema
                  .check_response({{"id", nullptr},
                                   {"error", {{"code", "parse_error"}, {"message", "x"}, {"retryable", false}}}},
                                  "")
                  .empty());
}

TEST(Types, HelloAndColormapsAndBase64)
{
  const HelloInfo hello = HelloInfo::from_json(
      {{"protocol", 1},
       {"server", {{"name", "stk-desktop-bridge"}, {"version", "1.0.0"}, {"python", "3.12"}, {"platform", "linux"},
                   {"pid", 42}}},
       {"methods", {"hello", "hub.policy"}},
       {"events", {"logs.chunk"}},
       {"limits", {{"max_line_bytes", 1000}, {"max_inflight", 8}, {"watch_interval_s", 2.0},
                   {"log_chunk_bytes", 5}, {"transfer_chunk_bytes", 6}}},
       {"paths", {{"state_dir", "/s"}, {"cache_dir", "/c"}, {"blob_dir", "/c/blobs"}, {"download_dir", "/c/d"}}},
       {"resumed_transfers", {std::string(32, 'f')}},
       {"future_key", true}});
  EXPECT_EQ(hello.server.pid, 42);
  EXPECT_TRUE(hello.has_method("hub.policy"));
  EXPECT_FALSE(hello.has_method("graph.evaluate"));
  EXPECT_EQ(hello.limits.max_line_bytes, 1000);
  EXPECT_EQ(hello.paths.blob_dir, "/c/blobs");
  EXPECT_EQ(hello.resumed_transfers.size(), 1u);
  EXPECT_TRUE(hello.raw.contains("future_key")); /* open results keep unknown keys */

  EXPECT_EQ(*decode_base64("aGVsbG8="), std::vector<uint8_t>({'h', 'e', 'l', 'l', 'o'}));
  EXPECT_EQ(*decode_base64("aGVsbG8"), std::vector<uint8_t>({'h', 'e', 'l', 'l', 'o'}));
  EXPECT_FALSE(decode_base64("a$==").has_value());
  EXPECT_FALSE(decode_base64("a").has_value());
  EXPECT_TRUE(decode_base64("")->empty());

  std::string lut;
  for (int i = 0; i < 1024 / 4; i++) {
    lut += "AAAA/w=="; /* 4 bytes per 8 chars incl. padding would be wrong: build real base64 below */
  }
  std::vector<uint8_t> bytes(1024);
  for (size_t i = 0; i < bytes.size(); i++) {
    bytes[i] = uint8_t(i * 7);
  }
  static const char *alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string b64;
  for (size_t i = 0; i < bytes.size(); i += 3) {
    const uint32_t chunk = (uint32_t(bytes[i]) << 16) | (i + 1 < bytes.size() ? uint32_t(bytes[i + 1]) << 8 : 0) |
                           (i + 2 < bytes.size() ? uint32_t(bytes[i + 2]) : 0);
    b64 += alphabet[(chunk >> 18) & 63];
    b64 += alphabet[(chunk >> 12) & 63];
    b64 += i + 1 < bytes.size() ? alphabet[(chunk >> 6) & 63] : '=';
    b64 += i + 2 < bytes.size() ? alphabet[chunk & 63] : '=';
  }
  const ColormapList maps = ColormapList::from_json(
      {{"colormaps", {{{"name", "viridis"}, {"lut_rgba8", b64}}}}, {"aliases", Json::object()},
       {"categorical_palettes", Json::array()}});
  ASSERT_EQ(maps.colormaps.size(), 1u);
  EXPECT_EQ(maps.colormaps[0].lut_rgba8[5], uint8_t(35));
  EXPECT_THROW(ColormapList::from_json({{"colormaps", {{{"name", "x"}, {"lut_rgba8", lut.substr(0, 12)}}}}}),
               std::runtime_error);
}

TEST(Types, Wp11HubAdditions)
{
  const HubPolicy policy = HubPolicy::from_json(
      {{"policy",
        {{"device_profile", "desktop"}, {"desktop_auto", true}, {"desktop_auto_bytes", 268435456},
         {"graph_auto_seconds", 300}, {"uploads", true}, {"upload_max_bytes", 1 << 30},
         {"read_kinds", {"logs", "events"}}, {"review_policy", "not-self"}}}});
  EXPECT_EQ(policy.device_profile, "desktop");
  EXPECT_TRUE(policy.desktop_auto);
  EXPECT_EQ(policy.desktop_auto_bytes, 268435456);
  EXPECT_EQ(policy.read_kinds.size(), 2u);
  EXPECT_EQ(policy.review_policy, "not-self");
  const Json action = {{"id", std::string(32, 'a')}, {"kind", "workspace.import"}, {"state", "review"}};
  const Transfer transfer = Transfer::from_json({{"id", std::string(32, 'b')}, {"kind", "upload"},
                                                 {"state", "running"}, {"action", action}});
  ASSERT_TRUE(transfer.action);
  EXPECT_TRUE(transfer.action->in_review());
  const CancelResult cancel = CancelResult::from_json(
      {{"cancelled", false}, {"error", {{"code", "remote_error"}, {"message", "unknown"}, {"retryable", false}}}});
  EXPECT_FALSE(cancel.cancelled);
  ASSERT_TRUE(cancel.error);
  EXPECT_EQ(cancel.error->code, ErrorCode::RemoteError);
  EXPECT_EQ(ConnectionInfo::from_json({{"id", "hub:lab"}, {"kind", "hub"}, {"name", "lab"}, {"url", nullptr},
                                       {"profile", "desktop"}})
                .profile,
            "desktop");
  /* An approval the hub's review policy refuses. */
  const Error refused = Error::from_json({{"code", "unauthorized"}, {"message", "not-self"}, {"retryable", false},
                                          {"data", {{"action_id", "a"}, {"reason", "review_policy"}}}});
  EXPECT_EQ(refused.code, ErrorCode::Unauthorized);
  EXPECT_EQ(refused.data["reason"], "review_policy");
  const ProtocolSchema &schema = ProtocolSchema::embedded();
  EXPECT_TRUE(schema.check_request({{"id", 1}, {"method", "hub.policy"}, {"params", {{"connection", "hub:lab"}}}})
                  .empty());
  EXPECT_TRUE(schema.check_response({{"id", 1}, {"result", policy.raw}}, "hub.policy").empty());
  EXPECT_TRUE(schema.check_request({{"id", 1}, {"method", "graph.cancel"},
                                    {"params", {{"eval_id", "e"}, {"connection", "hub:lab"},
                                                {"node", std::string(32, 'c')}}}})
                  .empty());
}

TEST(Types, ParamsBuildClosedObjects)
{
  LogsParams logs;
  logs.target = {"runtime:rt", ""};
  logs.task_id = "t1";
  logs.offsets = {{"stdout", 12}};
  logs.chunk_bytes = 64;
  const Json p = logs.to_json();
  EXPECT_EQ(p["connection"], "runtime:rt");
  EXPECT_FALSE(p.contains("node"));
  EXPECT_EQ(p["offsets"]["stdout"], 12);
  EXPECT_FALSE(p.contains("streams"));
  EvaluateParams eval;
  eval.eval_id = "e1";
  eval.request = {{"preset", "muferro-domains"}};
  eval.local_bindings = {{"run", "/data/run"}};
  const Json e = eval.to_json();
  EXPECT_FALSE(e.contains("mode"));
  EXPECT_FALSE(e.contains("connection"));
  EXPECT_EQ(e["local_bindings"]["run"], "/data/run");
  UploadParams upload;
  upload.target = {"runtime:rt", ""};
  upload.workspace_id = std::string(32, 'a');
  upload.source = "/data/in.bin";
  upload.idempotency_key = "up-1";
  DownloadParams download;
  download.target = {"runtime:rt", ""};
  download.task_id = "t1";
  download.path = "out.bin";
  download.idempotency_key = "dl-1";
  const ProtocolSchema &schema = ProtocolSchema::embedded();
  EXPECT_TRUE(schema.check_request({{"id", 1}, {"method", "upload.start"}, {"params", upload.to_json()}}).empty());
  EXPECT_TRUE(
      schema.check_request({{"id", 1}, {"method", "download.start"}, {"params", download.to_json()}}).empty());
  /* logs.end offsets are typed now; logs.chunk / events.batch carry `bytes`. */
  EXPECT_TRUE(schema.check_event({{"event", "logs.end"}, {"data", {{"sub", std::string(32, 'a')},
                                                                   {"offsets", {{"stdout", 5}}}}}})
                  .empty());
  EXPECT_FALSE(schema.check_event({{"event", "logs.end"}, {"data", {{"sub", std::string(32, 'a')},
                                                                    {"offsets", {{"stdout", "5"}}}}}})
                   .empty());
  EXPECT_FALSE(schema.check_event({{"event", "logs.end"}, {"data", {{"sub", std::string(32, 'a')},
                                                                    {"offsets", {{"stdin", 5}}}}}})
                   .empty());
  EXPECT_TRUE(schema.check_event({{"event", "logs.chunk"},
                                  {"data", {{"sub", std::string(32, 'a')}, {"stream", "stdout"}, {"text", "\xef\xbf\xbd"},
                                            {"offset", 0}, {"next_offset", 1}, {"bytes", 1}}}})
                  .empty());
  EXPECT_TRUE(schema.check_request({{"id", 1}, {"method", "logs.subscribe"}, {"params", p}}).empty());
  EXPECT_TRUE(schema.check_request({{"id", 1}, {"method", "graph.evaluate"}, {"params", e}}).empty());
  HubSubscribeParams hub{"hub:lab", 7};
  EXPECT_TRUE(schema.check_request({{"id", 1}, {"method", "hub.subscribe"}, {"params", hub.to_json()}}).empty());
}

TEST(Future, CompletesOnceAndChainsThroughMap)
{
  auto state = std::make_shared<detail::FutureState<Json>>(Executor());
  Future<Json> future(state);
  Future<int> mapped = future.map([](const Json &j) { return j["v"].get<int>() * 2; });
  int seen = 0;
  mapped.then([&](Result<int> r) { seen = r.value(); });
  EXPECT_FALSE(mapped.ready());
  EXPECT_TRUE(state->complete(Json{{"v", 21}}));
  EXPECT_FALSE(state->complete(Json{{"v", 1}}));
  EXPECT_EQ(seen, 42);
  EXPECT_EQ(mapped.get().value(), 42);

  auto failing = std::make_shared<detail::FutureState<Json>>(Executor());
  Future<int> bad = Future<Json>(failing).map([](const Json &j) -> int { return j.at("missing").get<int>(); });
  failing->complete(Json::object());
  ASSERT_FALSE(bad.get().ok());
  EXPECT_EQ(bad.get().error().code, ErrorCode::InternalError);
  EXPECT_THROW(bad.get().value(), BridgeException);

  auto pending = std::make_shared<detail::FutureState<Json>>(Executor());
  int hooks = 0;
  pending->add_cancel_hook([&] { hooks++; });
  Future<int> child = Future<Json>(pending).map([](const Json &) { return 1; });
  child.cancel();
  EXPECT_EQ(child.get().error().code, ErrorCode::Cancelled);
  EXPECT_EQ(pending->get().error().code, ErrorCode::Cancelled); /* cancelling the map cancels the call */
  EXPECT_EQ(hooks, 1);
  EXPECT_TRUE(child.get().error().local);
}

TEST(Future, ContinuationsRunOnTheExecutor)
{
  std::vector<std::function<void()>> queued;
  Executor executor = [&](std::function<void()> fn) { queued.push_back(std::move(fn)); };
  auto state = std::make_shared<detail::FutureState<Json>>(executor);
  bool ran = false;
  Future<Json>(state).then([&](Result<Json>) { ran = true; });
  state->complete(Json::object());
  EXPECT_FALSE(ran);
  ASSERT_EQ(queued.size(), 1u);
  queued[0]();
  EXPECT_TRUE(ran);
}

TEST(LogRing, SplitsSanitizesAndBounds)
{
  LogRing ring(3, 32);
  ring.append_bytes("第一行\n第二");
  ring.append_bytes("行 \xff\n");
  ring.append_bytes("\xe8\xae");
  ring.append_bytes("\xa1 ok\n");
  auto lines = ring.lines_after(0);
  ASSERT_EQ(lines.size(), 3u);
  EXPECT_EQ(lines[0].text, "第一行");
  EXPECT_EQ(lines[1].text, "第二行 \xef\xbf\xbd");
  EXPECT_EQ(lines[2].text, "计 ok"); /* a character split across reads is joined */
  ring.append_line("client note");
  lines = ring.lines_after(0);
  ASSERT_EQ(lines.size(), 3u); /* capacity 3: the oldest was dropped */
  EXPECT_EQ(ring.dropped(), 1u);
  EXPECT_EQ(lines.back().source, LogRing::Source::Client);
  EXPECT_EQ(ring.lines_after(lines[1].seq).size(), 1u);
  ring.append_bytes(std::string(100, 'x') + "\n");
  EXPECT_LE(ring.lines_after(ring.last_seq() - 1).back().text.size(), 32u + 3u);
  ring.append_bytes("tail without newline");
  ring.flush();
  EXPECT_EQ(ring.lines_after(ring.last_seq() - 1).back().text, "tail without newline");
}

TEST(Python, ExplicitChoiceMustExist)
{
  PythonLookup lookup;
  lookup.configured = "/no/such/python3";
  std::string error;
  EXPECT_FALSE(find_python(lookup, error).has_value());
  EXPECT_NE(error.find("/no/such/python3"), std::string::npos);
#if !defined(_WIN32)
  lookup.configured = "/bin/sh"; /* any executable stands in for an interpreter path */
  EXPECT_EQ(find_python(lookup, error).value_or(""), "/bin/sh");
  lookup.configured.clear();
  lookup.bundled = {"/no/such/bundled"};
  lookup.path_names = {"sh"};
  if (!getenv("STK_PYTHON")) {
    EXPECT_TRUE(find_python(lookup, error).has_value());
  }
#endif
}

}  // namespace
}  // namespace stk::bridge

// SPDX-License-Identifier: MIT
// See ../LICENSE: this standalone CPU helper has an explicit MIT license boundary.
#include <rtc/rtc.hpp>
#include <nlohmann/json.hpp>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#ifdef _WIN32
#  include <fcntl.h>
#  include <io.h>
#endif

using Json = nlohmann::json;
using namespace std::chrono_literals;
namespace {
constexpr size_t kControl = 16 * 1024 * 1024, kBlob = 64 * 1024;
constexpr size_t kFragment = 32 * 1024, kHigh = 256 * 1024, kLow = 128 * 1024;
constexpr size_t kSignal = 256 * 1024;
std::mutex output_mutex;
void emit(char kind, const std::string &body)
{
  if (body.size() > kControl) throw std::runtime_error("output bound");
  std::lock_guard lock(output_mutex);
  uint32_t size = static_cast<uint32_t>(body.size() + 1);
  char header[4];
  for (int i = 0; i < 4; ++i) header[i] = static_cast<char>(size >> (24 - 8 * i));
  std::cout.write(header, 4).put(kind).write(body.data(), body.size()).flush();
  if (!std::cout) throw std::runtime_error("output closed");
}
void event(char kind, const Json &body) { emit(kind, body.dump()); }
std::string digest(const std::string &body)
{
  std::string out(32, '\0'); unsigned int size = 0;
  if (EVP_Digest(body.data(), body.size(), reinterpret_cast<unsigned char *>(out.data()),
                 &size, EVP_sha256(), nullptr) != 1 || size != 32)
    throw std::runtime_error("digest unavailable");
  return out;
}
std::string hex(const std::string &bytes)
{
  static constexpr char digits[] = "0123456789abcdef";
  std::string out; out.reserve(bytes.size() * 2);
  for (unsigned char c : bytes) { out += digits[c >> 4]; out += digits[c & 15]; }
  return out;
}
std::string fingerprint(rtc::CertificateFingerprint fp)
{
  if (fp.algorithm != rtc::CertificateFingerprint::Algorithm::Sha256 || !fp.isValid())
    throw std::runtime_error("SHA256 fingerprint required");
  std::string out; int high = -1;
  for (unsigned char c : fp.value) {
    if (c == ':') continue;
    int nibble = c >= '0' && c <= '9' ? c - '0' :
                 c >= 'A' && c <= 'F' ? c - 'A' + 10 :
                 c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
    if (nibble < 0) throw std::runtime_error("fingerprint encoding");
    if (high < 0) high = nibble;
    else { out += static_cast<char>(high * 16 + nibble); high = -1; }
  }
  if (out.size() != 32 || high >= 0) throw std::runtime_error("fingerprint size");
  return out;
}
void put64(std::string &body, uint64_t n)
{ for (int i = 0; i < 8; ++i) body += static_cast<char>(n >> (56 - 8 * i)); }
uint64_t get64(const std::string &body, size_t offset)
{
  uint64_t out = 0;
  for (size_t i = 0; i < 8; ++i) out = (out << 8) | static_cast<unsigned char>(body.at(offset+i));
  return out;
}
Json parse(const std::string &body, size_t maximum)
{
  if (body.size() > maximum) throw std::runtime_error("JSON bound");
  auto out = Json::parse(body);
  if (!out.is_object()) throw std::runtime_error("object required");
  return out;
}
void fields(const Json &value, std::initializer_list<const char *> names)
{
  if (value.size() != names.size()) throw std::runtime_error("field count");
  for (auto name : names) if (!value.contains(name)) throw std::runtime_error("missing field");
}
bool read_record(char &kind, std::string &body)
{
  unsigned char header[4];
  std::cin.read(reinterpret_cast<char *>(header), 4);
  if (std::cin.gcount() == 0 && std::cin.eof()) return false;
  if (std::cin.gcount() != 4) throw std::runtime_error("partial record");
  uint32_t size = 0; for (unsigned char c : header) size = (size << 8) | c;
  if (!size || size > kControl + 1) throw std::runtime_error("record bound");
  std::cin.get(kind); body.resize(size - 1);
  std::cin.read(body.data(), body.size());
  if (!std::cin) throw std::runtime_error("partial record");
  return true;
}
Json candidate_info(rtc::Candidate candidate)
{
  candidate.resolve(); std::ostringstream type, transport;
  type << candidate.type(); transport << candidate.transportType();
  return {{"family", candidate.family() == rtc::Candidate::Family::Ipv6 ? "ipv6" :
                       candidate.family() == rtc::Candidate::Family::Ipv4 ? "ipv4" : "unresolved"},
          {"type", type.str()}, {"transport", transport.str()},
          {"address", candidate.address().value_or("")}, {"port", candidate.port().value_or(0)}};
}
class Helper {
  std::shared_ptr<rtc::PeerConnection> pc_;
  std::shared_ptr<rtc::DataChannel> dc_;
  std::mutex mutex_;
  std::condition_variable wake_;
  bool stopped_ = false, ready_ = false, remote_description_ = false;
  std::string mode_, nonce_, remote_nonce_, binding_, failure_code_;
  uint64_t sending_id_ = 0, receiving_id_ = 0, receiving_next_ = 1;
  std::string pending_sha_, incoming_;
  char incoming_kind_ = 0;
  size_t incoming_total_ = 0;
  std::mutex assembly_mutex_;
  std::condition_variable assembly_wake_;
  std::thread watchdog_;
  bool watchdog_stop_ = false, assembly_expired_ = false;
  std::chrono::milliseconds assembly_timeout_{30000};
  std::chrono::steady_clock::time_point assembly_deadline_;
  struct AssemblyTimeout {};

  void clear_assembly()
  {
    std::lock_guard lock(assembly_mutex_);
    std::string().swap(incoming_); receiving_id_ = 0;
    assembly_wake_.notify_all();
  }
  void watch_assembly()
  {
    std::unique_lock lock(assembly_mutex_);
    while (!watchdog_stop_) {
      if (!receiving_id_) {
        assembly_wake_.wait(lock, [this] { return watchdog_stop_ || receiving_id_ != 0; });
        continue;
      }
      auto id = receiving_id_;
      auto deadline = assembly_deadline_;
      if (assembly_wake_.wait_until(lock, deadline, [this, id] {
            return watchdog_stop_ || receiving_id_ != id;
          })) continue;
      std::string().swap(incoming_); receiving_id_ = 0; assembly_expired_ = true;
      lock.unlock();
      // close can synchronously invoke callbacks: hold neither receive nor state mutex.
      fail("assembly_timeout");
      if (dc_) dc_->close();
      return;
    }
  }

  bool allowed(rtc::Candidate candidate) const
  {
    candidate.resolve();
    bool udp = candidate.transportType() == rtc::Candidate::TransportType::Udp;
    bool tcp = candidate.transportType() == rtc::Candidate::TransportType::TcpActive ||
               candidate.transportType() == rtc::Candidate::TransportType::TcpPassive ||
               candidate.transportType() == rtc::Candidate::TransportType::TcpSo ||
               candidate.transportType() == rtc::Candidate::TransportType::TcpUnknown;
    return (mode_ == "tcp" ? tcp : mode_ == "all" ? udp || tcp : udp) &&
           (mode_ != "ipv6" || candidate.family() == rtc::Candidate::Family::Ipv6);
  }
  std::string filter_sdp(const std::string &sdp) const
  {
    std::istringstream stream(sdp); std::string line, out;
    while (std::getline(stream, line)) {
      if (!line.empty() && line.back() == '\r') line.pop_back();
      if (line.rfind("a=candidate:", 0) == 0 && !allowed(rtc::Candidate(line.substr(2)))) continue;
      out += line + "\r\n";
    }
    return out;
  }
  void fail(const char *code = "transport_closed") noexcept
  {
    std::string reason;
    { std::lock_guard lock(mutex_);
      stopped_ = true;
      if (failure_code_.empty()) failure_code_ = code;
      reason = failure_code_;
    }
    wake_.notify_all();
    try { event('E', {{"code", reason}}); } catch (...) {}
  }
  void send_frame(const std::string &frame)
  {
    if (!dc_ || frame.size() > dc_->maxMessageSize()) throw std::runtime_error("channel limit");
    dc_->send(reinterpret_cast<const std::byte *>(frame.data()), frame.size());
  }
  void bind(std::shared_ptr<rtc::DataChannel> channel)
  {
    if (dc_ || channel->label() != "stk.peer/1") { channel->close(); fail(); return; }
    dc_ = channel;
    dc_->setBufferedAmountLowThreshold(kLow);
    dc_->onBufferedAmountLow([this] { wake_.notify_all(); });
    dc_->onClosed([this] { fail(); });
    dc_->onError([this](std::string) { fail(); });
    dc_->onMessage([this](rtc::binary value) {
      try { receive(std::string(reinterpret_cast<const char *>(value.data()), value.size())); }
      catch (const AssemblyTimeout &) { clear_assembly(); fail("assembly_timeout"); if (dc_) dc_->close(); }
      catch (...) { clear_assembly(); fail(); if (dc_) dc_->close(); }
    }, [this](std::string) { fail(); if (dc_) dc_->close(); });
    dc_->onOpen([this] {
      try {
        if (dc_->maxMessageSize() < kFragment + 25) throw std::runtime_error("message limit");
        send_frame("H" + nonce_);
      } catch (...) { fail(); }
    });
  }
  void handshake(const std::string &frame)
  {
    if (!remote_nonce_.empty() || frame.size() != 33) throw std::runtime_error("nonce frame");
    remote_nonce_ = frame.substr(1);
    auto local = pc_->localDescription();
    if (!local || !local->fingerprint()) throw std::runtime_error("local fingerprint unavailable");
    // localDescription's local fingerprint is generated from this helper's actual certificate.
    // remoteFingerprint is observed by the DTLS verifier, rather than asserted remote JSON.
    auto local_fp = fingerprint(*local->fingerprint());
    auto remote_fp = fingerprint(pc_->remoteFingerprint());
    std::array<std::string, 2> pairs{local_fp + nonce_, remote_fp + remote_nonce_};
    if (pairs[0] == pairs[1]) throw std::runtime_error("reflected binding");
    std::sort(pairs.begin(), pairs.end());
    binding_ = hex(digest(std::string("stk.peer.channel/1\0", 19) + pairs[0] + pairs[1]));
    rtc::Candidate a, b;
    if (!pc_->getSelectedCandidatePair(&a, &b)) throw std::runtime_error("selected pair unavailable");
    // Test-selected route constraints are checked against actual selection as well as signaling.
    if (!allowed(a) || !allowed(b)) throw std::runtime_error("selected route mismatch");
    { std::lock_guard lock(mutex_); ready_ = true; }
    event('R', {{"channel_binding", binding_}, {"local_fingerprint", hex(local_fp)},
                {"remote_fingerprint", hex(remote_fp)}, {"local_nonce", hex(nonce_)},
                {"remote_nonce", hex(remote_nonce_)}, {"selected_pair", {candidate_info(a), candidate_info(b)}},
                {"max_message_size", dc_->maxMessageSize()}});
    wake_.notify_all();
  }
  void receive(const std::string &frame)
  {
    if (frame.empty() || frame.size() > 65536) throw std::runtime_error("frame bound");
    if (frame[0] == 'H') { handshake(frame); return; }
    { std::lock_guard lock(mutex_); if (!ready_ || stopped_) throw std::runtime_error("not ready"); }
    if (frame[0] == 'A') {
      std::lock_guard lock(mutex_);
      if (frame.size() != 41 || get64(frame, 1) != sending_id_ ||
          pending_sha_.empty() || frame.substr(9) != pending_sha_) throw std::runtime_error("invalid ack");
      pending_sha_.clear(); wake_.notify_all(); return;
    }
    char kind = frame[0];
    if ((kind != 'D' && kind != 'B') || frame.size() < 25) throw std::runtime_error("fragment kind");
    auto id = get64(frame, 1), total = get64(frame, 9), offset = get64(frame, 17);
    size_t cap = kind == 'D' ? kControl : kBlob;
    if (total > cap || offset > total || frame.size() - 25 > total - offset ||
        frame.size() - 25 > kFragment) throw std::runtime_error("fragment bound");
    std::unique_lock assembly_lock(assembly_mutex_);
    if (assembly_expired_ || (receiving_id_ && std::chrono::steady_clock::now() >= assembly_deadline_)) {
      assembly_expired_ = true;
      throw AssemblyTimeout{};
    }
    if (!receiving_id_) {
      if (id != receiving_next_ || offset != 0) throw std::runtime_error("message order");
      receiving_id_ = id; incoming_kind_ = kind; incoming_total_ = total;
      assembly_deadline_ = std::chrono::steady_clock::now() + assembly_timeout_;
      assembly_wake_.notify_all();
    }
    if (id != receiving_id_ || kind != incoming_kind_ || total != incoming_total_ ||
        offset != incoming_.size() || (total != 0 && frame.size() == 25))
      throw std::runtime_error("fragment order");
    incoming_.append(frame, 25, std::string::npos);
    if (incoming_.size() == total) {
      auto complete = std::move(incoming_);
      incoming_.clear(); receiving_id_ = 0; ++receiving_next_;
      assembly_wake_.notify_all();
      assembly_lock.unlock();
      auto checksum = digest(complete);
      emit(kind, complete); // ACK only after bounded delivery to the owning local process.
      std::string ack("A"); put64(ack, id); ack += checksum; send_frame(ack);
    }
  }
public:
  explicit Helper(const Json &config)
  {
    fields(config, {"offerer", "route", "ice_servers", "relay_only", "assembly_timeout_ms"});
    if (!config["assembly_timeout_ms"].is_number_integer() ||
        config["assembly_timeout_ms"].get<int64_t>() < 200 ||
        config["assembly_timeout_ms"].get<int64_t>() > 30000)
      throw std::runtime_error("invalid assembly timeout");
    assembly_timeout_ = std::chrono::milliseconds(config["assembly_timeout_ms"].get<int64_t>());
    if (!config["offerer"].is_boolean() || !config["relay_only"].is_boolean() ||
        !config["route"].is_string() || !config["ice_servers"].is_array() ||
        config["ice_servers"].size() > 8) throw std::runtime_error("invalid config");
    mode_ = config["route"].get<std::string>();
    if (mode_ != "all" && mode_ != "udp" && mode_ != "tcp" && mode_ != "ipv6")
      throw std::runtime_error("invalid route");
    nonce_.resize(32);
    if (RAND_bytes(reinterpret_cast<unsigned char *>(nonce_.data()), nonce_.size()) != 1)
      throw std::runtime_error("nonce unavailable");
    rtc::Configuration c; c.iceServers.clear(); c.maxMessageSize = 65536;
    c.enableIceTcp = mode_ == "tcp" || mode_ == "all";
    c.iceTransportPolicy = config["relay_only"].get<bool>() ? rtc::TransportPolicy::Relay : rtc::TransportPolicy::All;
    for (auto &server : config["ice_servers"]) {
      if (!server.is_string() || server.get_ref<const std::string &>().size() > 4096)
        throw std::runtime_error("invalid ICE server");
      c.iceServers.emplace_back(server.get<std::string>());
    }
    pc_ = std::make_shared<rtc::PeerConnection>(c);
    try {
      pc_->onLocalDescription([this](rtc::Description d) {
        try { event('S', {{"type", d.typeString()}, {"sdp", filter_sdp(std::string(d))}}); }
        catch (...) { fail(); }
      });
      pc_->onLocalCandidate([this](rtc::Candidate candidate) {
        try { if (allowed(candidate)) event('I', {{"candidate", candidate.candidate()}, {"mid", candidate.mid()}}); }
        catch (...) { fail(); }
      });
      pc_->onStateChange([this](rtc::PeerConnection::State state) {
        try { event('T', {{"state", int(state)}}); } catch (...) { fail(); }
        if (state == rtc::PeerConnection::State::Failed || state == rtc::PeerConnection::State::Closed) fail();
      });
      pc_->onDataChannel([this](std::shared_ptr<rtc::DataChannel> channel) { bind(channel); });
      if (config["offerer"].get<bool>()) bind(pc_->createDataChannel("stk.peer/1"));
      watchdog_ = std::thread([this] { watch_assembly(); });
    } catch (...) {
      // A failed callback/thread setup does not run ~Helper. Synchronize any
      // registered raw-this callbacks before member destruction on this exit.
      { std::lock_guard lock(mutex_); stopped_ = true; }
      wake_.notify_all();
      { std::lock_guard lock(assembly_mutex_); watchdog_stop_ = true; }
      assembly_wake_.notify_all();
      if (watchdog_.joinable()) watchdog_.join();
      pc_->resetCallbacks();
      if (dc_) dc_->resetCallbacks();
      pc_->close(); dc_.reset(); pc_.reset();
      throw;
    }
  }
  ~Helper()
  {
    { std::lock_guard lock(mutex_); stopped_ = true; } wake_.notify_all();
    { std::lock_guard lock(assembly_mutex_); watchdog_stop_ = true; }
    assembly_wake_.notify_all();
    if (watchdog_.joinable()) watchdog_.join();
    // PC callbacks can still enter bind() and assign dc_. Stop and join those
    // synchronized callbacks before inspecting dc_ or resetting its callbacks.
    pc_->resetCallbacks();
    if (dc_) dc_->resetCallbacks();
    pc_->close(); dc_.reset(); pc_.reset();
  }
  void signal(char kind, const std::string &body)
  {
    auto value = parse(body, kind == 'S' ? kSignal : 8192);
    if (kind == 'S') {
      { std::lock_guard lock(mutex_);
        if (ready_ || remote_description_) throw std::runtime_error("renegotiation is unsupported");
        remote_description_ = true;
      }
      fields(value, {"type", "sdp"});
      auto type = value["type"].get<std::string>();
      if (type != "offer" && type != "answer") throw std::runtime_error("description type");
      rtc::Description d(filter_sdp(value["sdp"].get<std::string>()), type);
      if (!d.fingerprint() || d.fingerprint()->algorithm != rtc::CertificateFingerprint::Algorithm::Sha256)
        throw std::runtime_error("remote fingerprint algorithm");
      pc_->setRemoteDescription(d);
    } else {
      fields(value, {"candidate", "mid"});
      rtc::Candidate candidate(value["candidate"].get<std::string>(), value["mid"].get<std::string>());
      if (allowed(candidate)) pc_->addRemoteCandidate(candidate);
    }
  }
  void send(char kind, const std::string &body)
  {
    if (body.size() > (kind == 'D' ? kControl : kBlob)) throw std::runtime_error("payload bound");
    auto checksum = digest(body);
    uint64_t id;
    { std::lock_guard lock(mutex_);
      if (!ready_ || stopped_ || !pending_sha_.empty() || sending_id_ == std::numeric_limits<uint64_t>::max())
        throw std::runtime_error("channel unavailable");
      id = ++sending_id_; pending_sha_ = checksum;
    }
    auto deadline = std::chrono::steady_clock::now() + 30s;
    size_t offset = 0;
    do {
      size_t count = std::min(kFragment, body.size() - offset);
      { std::unique_lock lock(mutex_);
        if (!wake_.wait_until(lock, deadline, [this, count] {
              return stopped_ || dc_->bufferedAmount() + count + 25 <= kHigh;
            }) || stopped_) throw std::runtime_error("backpressure timeout");
      }
      std::string frame(1, kind); put64(frame, id); put64(frame, body.size()); put64(frame, offset);
      frame.append(body, offset, count); send_frame(frame); offset += count;
    } while (offset < body.size());
    { std::unique_lock lock(mutex_);
      if (!wake_.wait_until(lock, deadline, [this] { return stopped_ || pending_sha_.empty(); }) || stopped_)
        throw std::runtime_error("ack timeout");
    }
    event('A', {{"message_id", id}, {"sha256", hex(checksum)}, {"kind", kind == 'D' ? "control" : "blob"}});
  }
};
} // namespace
int main()
{
#ifdef _WIN32
  _setmode(_fileno(stdin), _O_BINARY); _setmode(_fileno(stdout), _O_BINARY);
#endif
  rtc::InitLogger(rtc::LogLevel::None); rtc::SetThreadPoolSize(4);
  int result = 0;
  try {
    char kind; std::string body;
    if (!read_record(kind, body) || kind != 'C') throw std::runtime_error("config required");
    {
      Helper helper(parse(body, 65536));
      while (read_record(kind, body)) {
        if (kind == 'Q' && body.empty()) break;
        if (kind == 'S' || kind == 'I') helper.signal(kind, body);
        else if (kind == 'D' || kind == 'B') helper.send(kind, body);
        else throw std::runtime_error("invalid command");
      }
    }
  } catch (...) { result = 2; try { event('E', {{"code", "transport_closed"}}); } catch (...) {} }
  rtc::Cleanup().wait(); return result;
}

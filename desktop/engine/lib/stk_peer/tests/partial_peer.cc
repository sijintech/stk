// SPDX-License-Identifier: MIT
// Opt-in adversarial test peer. Never installed or included in the Python package.
#include <rtc/rtc.hpp>
#include <openssl/evp.h>
#include <atomic>
#include <chrono>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
using namespace std::chrono_literals;
namespace {
std::mutex output_mutex;
void output(const std::string &value)
{ std::lock_guard lock(output_mutex); std::cout << value << std::endl; }
std::string encode(const std::string &value)
{
  std::string out(4 * ((value.size() + 2) / 3), '\0');
  EVP_EncodeBlock(reinterpret_cast<unsigned char *>(out.data()),
                  reinterpret_cast<const unsigned char *>(value.data()), value.size());
  return out;
}
std::string decode(const std::string &value)
{
  std::string out(value.size(), '\0');
  int size = EVP_DecodeBlock(reinterpret_cast<unsigned char *>(out.data()),
                             reinterpret_cast<const unsigned char *>(value.data()), value.size());
  if (size < 0) throw std::runtime_error("encoding");
  if (!value.empty() && value.back() == '=') --size;
  if (value.size() > 1 && value[value.size()-2] == '=') --size;
  out.resize(size); return out;
}
void put64(std::string &value, uint64_t n)
{ for (int i = 0; i < 8; ++i) value += static_cast<char>(n >> (56 - 8 * i)); }
}
int main(int argc, char **argv)
{
  if (argc != 2 || (std::string(argv[1]) != "idle" && std::string(argv[1]) != "drip")) return 2;
  rtc::InitLogger(rtc::LogLevel::None); rtc::SetThreadPoolSize(4);
  std::atomic<bool> stopped = false, handshake = false;
  std::thread sender;
  rtc::Configuration config; config.iceServers.clear(); config.maxMessageSize = 65536;
  auto pc = std::make_shared<rtc::PeerConnection>(config);
  pc->onLocalDescription([](rtc::Description value) {
    output("S " + value.typeString() + " " + encode(std::string(value)));
  });
  pc->onLocalCandidate([](rtc::Candidate value) {
    output("I " + encode(value.mid()) + " " + encode(value.candidate()));
  });
  auto channel = pc->createDataChannel("stk.peer/1");
  channel->onOpen([channel] { channel->send(reinterpret_cast<const std::byte *>("Hqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"), 33); });
  channel->onClosed([&] { stopped = true; });
  channel->onMessage([&](rtc::binary value) {
    if (value.size() != 33 || value[0] != std::byte{'H'} || handshake.exchange(true)) return;
    sender = std::thread([&, channel] {
      try {
        size_t count = std::string(argv[1]) == "drip" ? 30 : 1;
        for (size_t offset = 0; offset < count && !stopped; ++offset) {
          std::string frame("D"); put64(frame, 1); put64(frame, 16 * 1024 * 1024);
          put64(frame, offset); frame += 'x';
          channel->send(reinterpret_cast<const std::byte *>(frame.data()), frame.size());
          output("E fragment " + std::to_string(offset + 1));
          if (count > 1) std::this_thread::sleep_for(100ms);
        }
      } catch (...) { output("E sender_closed"); }
    });
  }, [](std::string) {});
  int result = 0;
  try {
    std::string line;
    while (std::getline(std::cin, line)) {
      std::istringstream stream(line); std::string kind, a, b; stream >> kind >> a >> b;
      if (kind == "Q") break;
      if (kind == "S") pc->setRemoteDescription(rtc::Description(decode(b), a));
      else if (kind == "I") pc->addRemoteCandidate(rtc::Candidate(decode(b), decode(a)));
      else throw std::runtime_error("command");
    }
  } catch (...) { result = 3; }
  stopped = true;
  pc->resetCallbacks(); channel->resetCallbacks();
  if (sender.joinable()) sender.join();
  pc->close(); channel.reset(); pc.reset(); rtc::Cleanup().wait(); return result;
}

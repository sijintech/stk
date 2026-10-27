/* SPDX-License-Identifier: GPL-2.0-or-later */

#include "fixture.hh"
#include "evidence_pixels.hh"

#include <array>
#include <atomic>
#include <iterator>
#include <string>
#include <utility>
#include <vector>

namespace stk::document_preview {
namespace {

// Process-local fixture identities, not project persistence or authentication identities.
std::atomic<uint64_t> next_session{1};

std::string session_id(std::string &error)
{
  constexpr uint64_t maximum = 0xffffffffffffULL;
  uint64_t value = next_session.load(std::memory_order_relaxed);
  do {
    if (value > maximum) {
      error = "The native-preview fixture session counter is exhausted.";
      return {};
    }
  } while (!next_session.compare_exchange_weak(
      value, value + 1, std::memory_order_relaxed, std::memory_order_relaxed));
  std::string result = "a1111111-2222-4333-8444-000000000000";
  constexpr char hex[] = "0123456789abcdef";
  for (size_t i = 0; i < 12; ++i) {
    result[result.size() - 1 - i] = hex[value & 15];
    value >>= 4;
  }
  return result;
}

std::vector<uint8_t> bytes(std::string_view text)
{
  return {text.begin(), text.end()};
}

constexpr std::string_view kStyle = R"HTML(
<style>
* { box-sizing: border-box; }
body { margin: 0; background: #eff5fb; color: #142638;
       font: 17px/1.6 system-ui, sans-serif; }
main { max-width: 940px; padding: 28px; margin: auto; }
header { padding: 22px 28px; background: #164e82; color: white; }
h1 { margin: 0; font-size: 26px; } h2 { color: #174e7d; }
section { background: white; border: 1px solid #a4bbcf; border-radius: 8px;
          padding: 20px; margin-bottom: 24px; }
a { color: #064eaf; text-decoration: underline; }
nav { display: flex; flex-wrap: wrap; gap: 12px 24px; }
textarea, input { display: block; width: 100%; margin: 10px 0 16px;
                  padding: 10px; font: inherit; border: 2px solid #627e98; }
textarea { min-height: 130px; resize: vertical; }
pre { white-space: pre-wrap; background: #102b40; color: #f3f6f8; padding: 16px; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; border: 1px solid #9eb5c8; padding: 9px 12px; }
th { background: #d8e9f7; } tbody tr:nth-child(even) { background: #edf4f9; }
.notice { border-left: 6px solid #db6b16; background: #fff0dc; padding: 14px; }
.image { width: 192px; height: 192px; image-rendering: pixelated; border: 4px solid #183f61; }
.math { font-size: 22px; color: #68380c; }
footer { border-top: 4px solid #cf6225; padding: 24px 0 40px; }
</style>
)HTML";

std::string evidence_stripe(int page)
{
  std::string result = "<div aria-label=\"Native capture marker\" style=\"display:flex;height:24px;overflow:hidden\">";
  for (int i = 0; i < 6; ++i) {
    const auto &c = kEvidenceColors[page == 1 ? i : 5 - i];
    result += "<span style=\"flex:none;width:20px;height:24px;background:rgb(" +
        std::to_string(c[0]) + "," + std::to_string(c[1]) + "," + std::to_string(c[2]) +
        ")\"></span>";
  }
  return result + "</div>";
}

std::string index_html()
{
  std::string html = R"HTML(<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>STK 离线文档嵌入验收夹具</title>
)HTML";
  html += kStyle;
  html += "</head><body>" + evidence_stripe(1);
  html += R"HTML(
<header><h1>STK 文档预览 · 合成验收夹具</h1>
<p>中文 / English — static content, no scripts or external assets</p></header>
<main>
<section><p class="notice">这是一组原型验收内容，不代表 Markdown、报告或 PDF 阅读体验已完成。</p>
<nav aria-label="本地夹具导航">
<a href="next.html">打开下一页 / Next page</a>
<a href="fixture.pdf">打开两页 PDF / Two-page PDF</a>
<a href="#footer">滚动到页尾 / Footer</a></nav></section>
<section><h2>输入法、选择与剪贴板</h2>
<label for="ime-line">在此输入中英文，再尝试选择、复制、粘贴（不保存）：</label>
<input id="ime-line" type="text" autocomplete="off" spellcheck="false"
       value="中文输入检查 / IME and clipboard check">
<label for="ime-multiline">多行输入区域：</label>
<textarea id="ime-multiline" autocomplete="off" spellcheck="false">第一行：合成文档。
Second line: select and copy this text.
第三行：输入不会保存到项目，也不会提交任务。</textarea>
<p>切换到原生控件、隐藏文档区域后检查焦点是否正确移出。</p></section>
<section><h2>同一清单内的图片</h2>
<img class="image" src="%E5%9B%BE%20%E5%83%8F%23%25.png" width="192" height="192"
     alt="蓝色和橙色的合成棋盘格">
<p>资源名：<code>图 像#%.png</code>。蓝橙棋盘格应完整显示，无需网络。</p></section>
<section><h2>代码与静态数学文本</h2>
<pre><code># Display only — this code is never executed.
samples = [1, 2, 3, 4]
mean = sum(samples) / len(samples)
print("synthetic fixture", mean)</code></pre>
<p class="math">x̄ = (x₁ + x₂ + ··· + xₙ) / n</p>
<p class="math">E = mc² &nbsp; · &nbsp; ∑ᵢ xᵢ = 10</p>
<p>数学内容是静态 Unicode 文本，不使用 LaTeX 编译器或数学脚本。</p></section>
<section><h2>可滚动的合成数据表</h2>
<p>下面的数值仅用于排版、文字选择和滚动验收，不是测量或仿真结果。</p>
<table><thead><tr><th>序号</th><th>合成标签</th><th>示例值</th></tr></thead><tbody>
)HTML";
  for (int row = 1; row <= 24; ++row) {
    html += "<tr><td>" + std::to_string(row) + "</td><td>合成样例 " + std::to_string(row) +
            " / Synthetic sample</td><td>" + std::to_string(row * 3) + "</td></tr>\n";
  }
  html += R"HTML(</tbody></table></section>
<section><h2>必须拒绝的动作</h2>
<p>以下链接用于明确点击后的阻断验收；页面不会自动请求它们。</p>
<nav aria-label="拒绝动作检查">
<a href="https://example.invalid/stk-preview-check">外部链接（应拒绝）</a>
<a href="next.html" target="_blank" rel="noopener noreferrer">新窗口（应拒绝）</a>
<a href="fixture.pdf" download="fixture.pdf">下载 PDF（应拒绝）</a>
</nav></section>
<footer id="footer"><strong>页尾 / End of the scroll fixture</strong>
<p><a href="next.html">下一页</a> · <a href="fixture.pdf">两页 PDF</a> ·
<a href="#">返回页首</a></p></footer>
</main></body></html>
)HTML";
  return html;
}

std::string next_html()
{
  std::string html = R"HTML(<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>STK 本地导航第二页</title>
)HTML";
  html += kStyle;
  html += "</head><body>" + evidence_stripe(2);
  html += R"HTML(
<header style="background:#88470f"><h1>第二页 / Local page two</h1></header>
<main><section><h2>本地导航成功后应看到橙色标题</h2>
<p>内容仍来自此次预览会话内的清单。这里没有脚本、远程图片或字体。</p>
<nav><a href="index.html">返回首页 / Back to index</a>
<a href="fixture.pdf">打开两页 PDF</a></nav></section>
<section><p>复制检查：合成文档的第二页。Synthetic page two.</p></section>
</main></body></html>
)HTML";
  return html;
}

// Our own 16x16 RGBA checkerboard, four-pixel blue/orange squares. PNG chunks contain a zlib
// stream and CRCs; no image library, external artwork or filesystem is needed at runtime.
constexpr uint8_t kCheckerboard[] = {
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d,
    0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x10,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0xf3, 0xff, 0x61, 0x00, 0x00, 0x00,
    0x27, 0x49, 0x44, 0x41, 0x54, 0x78, 0xda, 0x63, 0x90, 0x6f, 0x39, 0xf9,
    0x1f, 0x19, 0xbf, 0x89, 0x30, 0x43, 0xc1, 0x84, 0xe4, 0x19, 0x86, 0x81,
    0x01, 0xa4, 0x6a, 0x40, 0x97, 0x1f, 0x0e, 0x06, 0x8c, 0xa6, 0x83, 0xd1,
    0x74, 0x00, 0xc4, 0x00, 0x1f, 0x89, 0x72, 0x1f, 0xf9, 0x5f, 0xd9, 0x86,
    0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae, 0x42, 0x60, 0x82,
};

std::string pdf_stripe_image(int page)
{
  // One page-owned raster avoids separately antialiased rectangle edges creating
  // artificial gaps between adjacent colors. The OS screenshot still has to pass
  // the unchanged contiguous-color criterion after the browser renders this PDF.
  constexpr int width = 960, height = 96;
  std::string pixels;
  pixels.reserve(width * height * 3);
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      const size_t index = size_t(x) * kEvidenceColors.size() / width;
      const auto &color = kEvidenceColors[page == 1 ? index : kEvidenceColors.size() - 1 - index];
      for (const auto channel : color) { pixels.push_back(char(channel)); }
    }
  }
  return "<< /Type /XObject /Subtype /Image /Width " + std::to_string(width) +
      " /Height " + std::to_string(height) +
      " /ColorSpace /DeviceRGB /BitsPerComponent 8 /Interpolate false /Length " +
      std::to_string(pixels.size()) + " >>\nstream\n" + pixels + "\nendstream";
}

std::string pdf_fixture()
{
  // Standard Type1 Helvetica and uncompressed English text avoid a font/renderer dependency.
  // Every xref offset and stream length is computed from the actual bytes emitted below.
  const std::string first =
      "q 0.90 0.95 1 rg 0 0 612 792 re f Q\n"
      "q 240 0 0 24 48 650 cm /Marker Do Q\n"
      "BT /F1 24 Tf 0.06 0.22 0.38 rg 48 714 Td (Synthetic PDF - page 1 of 2) Tj\n"
      "/F1 14 Tf 0 -110 Td (Offline document preview acceptance fixture.) Tj\n"
      "0 -30 Td (Select, copy, search, zoom and scroll to the next page.) Tj\n"
      "0 -30 Td (These are synthetic words, not scientific results.) Tj\n"
      "0 -30 Td (No scripts, embedded files, links or external fonts.) Tj ET\n";
  const std::string second =
      "q 1 0.94 0.86 rg 0 0 612 792 re f Q\n"
      "q 240 0 0 24 48 650 cm /Marker Do Q\n"
      "BT /F1 24 Tf 0.47 0.22 0.04 rg 48 714 Td (Synthetic PDF - page 2 of 2) Tj\n"
      "/F1 14 Tf 0 -110 Td (The second page has a pale orange background.) Tj\n"
      "0 -30 Td (Search marker: STK-PDF-PAGE-TWO.) Tj\n"
      "0 -30 Td (Close or hide the view and verify focus returns to STK.) Tj\n"
      "0 -30 Td (Native PDF support remains subject to platform acceptance.) Tj ET\n";
  const std::string page =
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
      "/Resources << /Font << /F1 5 0 R >> /XObject << /Marker ";
  const std::array<std::string, 9> objects = {
      "<< /Type /Catalog /Pages 2 0 R >>",
      "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
      page + "8 0 R >> >> /Contents 6 0 R >>",
      page + "9 0 R >> >> /Contents 7 0 R >>",
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
      "<< /Length " + std::to_string(first.size()) + " >>\nstream\n" + first + "endstream",
      "<< /Length " + std::to_string(second.size()) + " >>\nstream\n" + second + "endstream",
      pdf_stripe_image(1),
      pdf_stripe_image(2),
  };
  std::string pdf = "%PDF-1.4\n% STK synthetic acceptance fixture\n";
  std::array<size_t, 9> offsets{};
  for (size_t i = 0; i < objects.size(); ++i) {
    offsets[i] = pdf.size();
    pdf += std::to_string(i + 1) + " 0 obj\n" + objects[i] + "\nendobj\n";
  }
  const size_t xref = pdf.size();
  const auto object_count = std::to_string(objects.size() + 1);
  pdf += "xref\n0 " + object_count + "\n0000000000 65535 f \n";
  for (const size_t offset : offsets) {
    const auto digits = std::to_string(offset);
    pdf += std::string(10 - digits.size(), '0') + digits + " 00000 n \n";
  }
  pdf += "trailer\n<< /Size " + object_count + " /Root 1 0 R >>\nstartxref\n" +
      std::to_string(xref) + "\n%%EOF\n";
  return pdf;
}

}  // namespace

std::string make_pdf_fixture()
{
  return pdf_fixture();
}

std::shared_ptr<ResourceSession> make_fixture(std::string &error)
{
  error.clear();
  auto session = session_id(error);
  if (session.empty()) {
    return {};
  }
  PreviewIdentity identity{"10101010-2020-4030-8040-505050505050",
                           "61616161-7272-4383-8494-a5a5a5a5a5a5",
                           "fixture-v1",
                           std::move(session)};
  std::vector<ResourceAsset> assets;
  assets.push_back({"index.html", "text/html", bytes(index_html())});
  assets.push_back({"next.html", "text/html", bytes(next_html())});
  assets.push_back({"图 像#%.png", "image/png", {std::begin(kCheckerboard), std::end(kCheckerboard)}});
  assets.push_back({"fixture.pdf", "application/pdf", bytes(pdf_fixture())});
  return ResourceSession::create(std::move(identity), std::move(assets), error);
}

}  // namespace stk::document_preview

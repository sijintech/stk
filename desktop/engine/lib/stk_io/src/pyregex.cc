/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "stk/io/pyregex.hh"

#include "stk/core/utf8.hh"

#include <algorithm>
#include <iterator>
#include <list>
#include <unordered_map>
#include <vector>

namespace stk::io {

namespace {

struct CodeRange {
  char32_t lo, hi;
};

#include "pyregex_tables.inc"

template<size_t N> bool in_table(const CodeRange (&table)[N], char32_t c)
{
  const auto it = std::upper_bound(
      std::begin(table), std::end(table), c, [](char32_t value, const CodeRange &r) { return value < r.lo; });
  return it != std::begin(table) && c <= std::prev(it)->hi;
}

bool is_digit(char32_t c)
{
  return in_table(kDigit, c);
}
bool is_word(char32_t c)
{
  return in_table(kWord, c);
}
bool is_space(char32_t c)
{
  return in_table(kSpace, c);
}

enum Category : uint8_t { kCatDigit = 1, kCatNotDigit = 2, kCatWord = 4, kCatNotWord = 8, kCatSpace = 16, kCatNotSpace = 32 };

struct CharClass {
  std::vector<CodeRange> ranges;
  uint8_t categories = 0;
  bool negate = false;

  bool contains(char32_t c) const
  {
    bool hit = false;
    for (const CodeRange &r : ranges) {
      if (c >= r.lo && c <= r.hi) {
        hit = true;
        break;
      }
    }
    if (!hit && categories) {
      hit = ((categories & kCatDigit) && is_digit(c)) || ((categories & kCatNotDigit) && !is_digit(c)) ||
            ((categories & kCatWord) && is_word(c)) || ((categories & kCatNotWord) && !is_word(c)) ||
            ((categories & kCatSpace) && is_space(c)) || ((categories & kCatNotSpace) && !is_space(c));
    }
    return hit != negate;
  }
};

enum class Assertion : uint8_t { Begin, End, EndOfString, WordBoundary, NotWordBoundary };

/* AST */
struct Node {
  enum Kind { Empty, Char, Any, Class, Concat, Alternate, Repeat, Assert, Look } kind = Empty;
  char32_t ch = 0;
  int cls = -1;
  Assertion assertion = Assertion::Begin;
  bool negative = false; /* Look: (?!...) */
  int min = 0, max = 0;  /* Repeat; max = -1: unbounded */
  std::vector<std::unique_ptr<Node>> children;
};

constexpr int kUnbounded = -1;
constexpr int kMaxRepeat = 4294967;   /* sre MAXREPEAT is larger; counts above this are rejected */
constexpr size_t kMaxProgram = 200000; /* instructions */

class Parser {
 public:
  Parser(std::u32string pattern, std::vector<CharClass> &classes) : p_(std::move(pattern)), classes_(classes) {}

  std::unique_ptr<Node> parse()
  {
    auto node = alternation();
    if (i_ < p_.size()) {
      error(p_[i_] == U')' ? "unbalanced parenthesis" : "unexpected character");
    }
    return node;
  }

 private:
  [[noreturn]] void error(const std::string &message) const
  {
    throw RegexError(message + " at position " + std::to_string(i_));
  }
  bool at_end() const
  {
    return i_ >= p_.size();
  }
  char32_t peek(size_t ahead = 0) const
  {
    return i_ + ahead < p_.size() ? p_[i_ + ahead] : U'\0';
  }
  bool accept(char32_t c)
  {
    if (!at_end() && p_[i_] == c) {
      i_++;
      return true;
    }
    return false;
  }

  std::unique_ptr<Node> make(Node::Kind kind)
  {
    auto node = std::make_unique<Node>();
    node->kind = kind;
    return node;
  }

  std::unique_ptr<Node> alternation()
  {
    auto first = concatenation();
    if (peek() != U'|') {
      return first;
    }
    auto node = make(Node::Alternate);
    node->children.push_back(std::move(first));
    while (accept(U'|')) {
      node->children.push_back(concatenation());
    }
    return node;
  }

  std::unique_ptr<Node> concatenation()
  {
    auto node = make(Node::Concat);
    while (!at_end() && peek() != U'|' && peek() != U')') {
      repeat(node->children);
    }
    return node;
  }

  /* Parses one atom and its quantifier (sre_parse: "nothing to repeat", "multiple repeat"). */
  void repeat(std::vector<std::unique_ptr<Node>> &items)
  {
    const char32_t c = peek();
    if (c == U'*' || c == U'+' || c == U'?' || c == U'{') {
      int min = 0, max = 0;
      const size_t here = i_;
      i_++;
      if (c == U'*') {
        max = kUnbounded;
      }
      else if (c == U'+') {
        min = 1;
        max = kUnbounded;
      }
      else if (c == U'?') {
        max = 1;
      }
      else {
        if (peek() == U'}') {
          items.push_back(literal(U'{'));
          return;
        }
        std::u32string lo, hi;
        while (peek() >= U'0' && peek() <= U'9') {
          lo.push_back(p_[i_++]);
        }
        bool comma = accept(U',');
        if (comma) {
          while (peek() >= U'0' && peek() <= U'9') {
            hi.push_back(p_[i_++]);
          }
        }
        else {
          hi = lo;
        }
        if (!accept(U'}')) {
          i_ = here + 1;
          items.push_back(literal(U'{'));
          return;
        }
        min = lo.empty() ? 0 : number(lo);
        max = hi.empty() ? kUnbounded : number(hi);
        if (max != kUnbounded && max < min) {
          error("min repeat greater than max repeat");
        }
      }
      if (items.empty() || items.back()->kind == Node::Assert) {
        error("nothing to repeat");
      }
      if (items.back()->kind == Node::Repeat) {
        error("multiple repeat");
      }
      if (accept(U'+')) {
        throw RegexError("possessive quantifiers are not supported");
      }
      accept(U'?'); /* lazy: same set of matches for search() */
      auto node = make(Node::Repeat);
      node->min = min;
      node->max = max;
      node->children.push_back(std::move(items.back()));
      items.back() = std::move(node);
      return;
    }
    auto atom_node = atom();
    if (atom_node) {
      items.push_back(std::move(atom_node));
    }
  }

  int number(const std::u32string &digits)
  {
    long long value = 0;
    for (char32_t d : digits) {
      value = value * 10 + (d - U'0');
      if (value > kMaxRepeat) {
        error("the repetition number is too large");
      }
    }
    return int(value);
  }

  std::unique_ptr<Node> literal(char32_t c)
  {
    auto node = make(Node::Char);
    node->ch = c;
    return node;
  }

  std::unique_ptr<Node> assertion(Assertion a)
  {
    auto node = make(Node::Assert);
    node->assertion = a;
    return node;
  }

  std::unique_ptr<Node> atom()
  {
    const char32_t c = p_[i_++];
    switch (c) {
      case U'(':
        return group();
      case U'[':
        return char_class();
      case U'.':
        return make(Node::Any);
      case U'^':
        return assertion(Assertion::Begin);
      case U'$':
        return assertion(Assertion::End);
      case U'\\':
        return escape();
      default:
        return literal(c);
    }
  }

  std::unique_ptr<Node> group()
  {
    std::unique_ptr<Node> node;
    if (accept(U'?')) {
      const char32_t kind = at_end() ? U'\0' : p_[i_++];
      if (kind == U':') {
        node = alternation();
      }
      else if (kind == U'=' || kind == U'!') {
        node = make(Node::Look);
        node->negative = kind == U'!';
        node->children.push_back(alternation());
      }
      else if (kind == U'P' && accept(U'<')) {
        while (!at_end() && peek() != U'>') {
          i_++;
        }
        if (!accept(U'>')) {
          error("missing >, unterminated name");
        }
        node = alternation();
      }
      else if (kind == U'#') {
        while (!at_end() && peek() != U')') {
          i_++;
        }
        if (!accept(U')')) {
          error("missing ), unterminated comment");
        }
        return nullptr;
      }
      else if (kind == U'<') {
        throw RegexError("lookbehind assertions are not supported");
      }
      else {
        throw RegexError("unsupported group syntax (?" + core::utf8::encode(kind) + "...");
      }
    }
    else {
      node = alternation();
    }
    if (!accept(U')')) {
      error("missing ), unterminated subpattern");
    }
    if (node->kind != Node::Look) {
      /* A group is one item: wrap so a following quantifier applies to all of it. */
      auto wrapper = make(Node::Concat);
      wrapper->children.push_back(std::move(node));
      return wrapper;
    }
    return node;
  }

  char32_t hex_digits(int count)
  {
    char32_t value = 0;
    for (int k = 0; k < count; k++) {
      const char32_t d = peek();
      int digit;
      if (d >= U'0' && d <= U'9') {
        digit = int(d - U'0');
      }
      else if (d >= U'a' && d <= U'f') {
        digit = int(d - U'a') + 10;
      }
      else if (d >= U'A' && d <= U'F') {
        digit = int(d - U'A') + 10;
      }
      else {
        error("incomplete escape");
      }
      value = value * 16 + char32_t(digit);
      i_++;
    }
    if (value > 0x10FFFF) {
      error("bad escape (code point out of range)");
    }
    return value;
  }

  /* Escapes shared by classes and the top level: returns true and sets `out` for a literal. */
  bool literal_escape(char32_t c, char32_t &out)
  {
    switch (c) {
      case U'a':
        out = 7;
        return true;
      case U'f':
        out = 12;
        return true;
      case U'n':
        out = 10;
        return true;
      case U'r':
        out = 13;
        return true;
      case U't':
        out = 9;
        return true;
      case U'v':
        out = 11;
        return true;
      case U'\\':
        out = U'\\';
        return true;
      case U'x':
        out = hex_digits(2);
        return true;
      case U'u':
        out = hex_digits(4);
        return true;
      case U'U':
        out = hex_digits(8);
        return true;
      default:
        return false;
    }
  }

  uint8_t category(char32_t c)
  {
    switch (c) {
      case U'd':
        return kCatDigit;
      case U'D':
        return kCatNotDigit;
      case U'w':
        return kCatWord;
      case U'W':
        return kCatNotWord;
      case U's':
        return kCatSpace;
      case U'S':
        return kCatNotSpace;
      default:
        return 0;
    }
  }

  static bool ascii_letter(char32_t c)
  {
    return (c >= U'a' && c <= U'z') || (c >= U'A' && c <= U'Z');
  }

  char32_t octal(char32_t first, int more)
  {
    char32_t value = first - U'0';
    for (int k = 0; k < more && peek() >= U'0' && peek() <= U'7'; k++) {
      value = value * 8 + (p_[i_++] - U'0');
    }
    if (value > 0377) {
      error("octal escape value outside of range 0-0o377");
    }
    return value;
  }

  std::unique_ptr<Node> escape()
  {
    if (at_end()) {
      error("bad escape (end of pattern)");
    }
    const char32_t c = p_[i_++];
    if (const uint8_t cat = category(c)) {
      CharClass cls;
      cls.categories = cat;
      classes_.push_back(std::move(cls));
      auto node = make(Node::Class);
      node->cls = int(classes_.size() - 1);
      return node;
    }
    switch (c) {
      case U'A':
        return assertion(Assertion::Begin);
      case U'Z':
        return assertion(Assertion::EndOfString);
      case U'b':
        return assertion(Assertion::WordBoundary);
      case U'B':
        return assertion(Assertion::NotWordBoundary);
      default:
        break;
    }
    char32_t value;
    if (literal_escape(c, value)) {
      return literal(value);
    }
    if (c == U'0') {
      return literal(octal(c, 2));
    }
    if (c >= U'1' && c <= U'9') {
      /* Three octal digits form an octal escape; anything else is a back-reference. */
      if (c <= U'7' && peek() >= U'0' && peek() <= U'7' && peek(1) >= U'0' && peek(1) <= U'7') {
        return literal(octal(c, 2));
      }
      throw RegexError("back-references are not supported");
    }
    if (c == U'N') {
      throw RegexError("\\N{...} escapes are not supported");
    }
    if (ascii_letter(c)) {
      error("bad escape \\" + core::utf8::encode(c));
    }
    return literal(c);
  }

  /* One class item: a literal code point (returns true) or a category added to `cls`. */
  bool class_item(char32_t c, CharClass &cls, char32_t &out)
  {
    if (c != U'\\') {
      out = c;
      return true;
    }
    if (at_end()) {
      error("bad escape (end of pattern)");
    }
    const char32_t e = p_[i_++];
    if (const uint8_t cat = category(e)) {
      cls.categories |= cat;
      return false;
    }
    if (e == U'b') {
      out = 8;
      return true;
    }
    if (literal_escape(e, out)) {
      return true;
    }
    if (e >= U'0' && e <= U'7') {
      out = octal(e, 2);
      return true;
    }
    if ((e >= U'0' && e <= U'9') || ascii_letter(e)) {
      error("bad escape \\" + core::utf8::encode(e));
    }
    out = e;
    return true;
  }

  std::unique_ptr<Node> char_class()
  {
    CharClass cls;
    cls.negate = accept(U'^');
    bool any = false;
    for (;;) {
      if (at_end()) {
        error("unterminated character set");
      }
      const char32_t c = p_[i_++];
      if (c == U']' && any) {
        break;
      }
      any = true;
      char32_t lo;
      const bool is_literal = class_item(c, cls, lo);
      if (peek() == U'-') {
        i_++;
        if (at_end()) {
          error("unterminated character set");
        }
        const char32_t d = p_[i_++];
        if (d == U']') {
          if (is_literal) {
            cls.ranges.push_back({lo, lo});
          }
          cls.ranges.push_back({U'-', U'-'});
          break;
        }
        char32_t hi;
        const bool hi_literal = class_item(d, cls, hi);
        if (!is_literal || !hi_literal) {
          error("bad character range");
        }
        if (hi < lo) {
          error("bad character range");
        }
        cls.ranges.push_back({lo, hi});
      }
      else if (is_literal) {
        cls.ranges.push_back({lo, lo});
      }
    }
    classes_.push_back(std::move(cls));
    auto node = make(Node::Class);
    node->cls = int(classes_.size() - 1);
    return node;
  }

  std::u32string p_;
  size_t i_ = 0;
  std::vector<CharClass> &classes_;
};

enum class Op : uint8_t { Char, Any, Class, Split, Jump, Assert, Look, Match };

struct Inst {
  Op op;
  bool negative = false;
  Assertion assertion = Assertion::Begin;
  char32_t ch = 0;
  int32_t x = 0, y = 0; /* Split targets / Jump target / Class index / Look: body start */
  int32_t look = -1;    /* Look: index of its memo */
};

}  // namespace

struct PyRegex::Program {
  std::vector<Inst> code;
  std::vector<CharClass> classes;
  int32_t start = 0;
  int32_t looks = 0;

  int32_t emit(Inst inst)
  {
    if (code.size() >= kMaxProgram) {
      throw RegexError("pattern too large");
    }
    code.push_back(inst);
    return int32_t(code.size() - 1);
  }

  void compile(const Node &node)
  {
    switch (node.kind) {
      case Node::Empty:
        return;
      case Node::Char:
        emit({Op::Char, false, Assertion::Begin, node.ch});
        return;
      case Node::Any:
        emit({Op::Any});
        return;
      case Node::Class: {
        Inst inst{Op::Class};
        inst.x = node.cls;
        emit(inst);
        return;
      }
      case Node::Concat:
        for (const auto &child : node.children) {
          compile(*child);
        }
        return;
      case Node::Alternate: {
        std::vector<int32_t> jumps;
        for (size_t k = 0; k < node.children.size(); k++) {
          if (k + 1 < node.children.size()) {
            const int32_t split = emit({Op::Split});
            code[split].x = split + 1;
            compile(*node.children[k]);
            jumps.push_back(emit({Op::Jump}));
            code[split].y = int32_t(code.size());
          }
          else {
            compile(*node.children[k]);
          }
        }
        for (int32_t j : jumps) {
          code[j].x = int32_t(code.size());
        }
        return;
      }
      case Node::Repeat: {
        const Node &body = *node.children[0];
        for (int k = 0; k < node.min; k++) {
          compile(body);
        }
        if (node.max == kUnbounded) {
          const int32_t split = emit({Op::Split});
          code[split].x = split + 1;
          compile(body);
          Inst jump{Op::Jump};
          jump.x = split;
          emit(jump);
          code[split].y = int32_t(code.size());
        }
        else {
          std::vector<int32_t> splits;
          for (int k = node.min; k < node.max; k++) {
            const int32_t split = emit({Op::Split});
            code[split].x = split + 1;
            splits.push_back(split);
            compile(body);
          }
          for (int32_t s : splits) {
            code[s].y = int32_t(code.size());
          }
        }
        return;
      }
      case Node::Assert: {
        Inst inst{Op::Assert};
        inst.assertion = node.assertion;
        emit(inst);
        return;
      }
      case Node::Look: {
        /* [Look -> body][Jump over body][body ... Match] */
        const int32_t look = emit({Op::Look});
        code[look].negative = node.negative;
        code[look].look = looks++;
        const int32_t jump = emit({Op::Jump});
        code[look].x = int32_t(code.size());
        compile(*node.children[0]);
        emit({Op::Match});
        code[jump].x = int32_t(code.size());
        return;
      }
    }
  }

  struct Memo {
    std::vector<std::vector<int8_t>> results; /* per look, per position: -1 unknown, 0/1 */
  };

  bool assertion_holds(Assertion a, const std::u32string &t, size_t pos) const
  {
    const size_t n = t.size();
    switch (a) {
      case Assertion::Begin:
        return pos == 0;
      case Assertion::End:
        return pos == n || (pos + 1 == n && t[pos] == U'\n');
      case Assertion::EndOfString:
        return pos == n;
      case Assertion::WordBoundary:
      case Assertion::NotWordBoundary: {
        if (n == 0) {
          return false;
        }
        const bool before = pos > 0 && is_word(t[pos - 1]);
        const bool after = pos < n && is_word(t[pos]);
        return (a == Assertion::WordBoundary) == (before != after);
      }
    }
    return false;
  }

  bool look_holds(const Inst &inst, const std::u32string &t, size_t pos, Memo &memo) const
  {
    std::vector<int8_t> &slot = memo.results[size_t(inst.look)];
    if (slot.empty()) {
      slot.assign(t.size() + 1, -1);
    }
    if (slot[pos] < 0) {
      slot[pos] = run(inst.x, t, pos, true, false, memo) ? 1 : 0;
    }
    return (slot[pos] == 1) != inst.negative;
  }

  /* Thompson simulation: is there a match of the program at `entry` starting at pos0 (anchored) or
   * at any position >= pos0, optionally ending at the end of the text? */
  bool run(int32_t entry, const std::u32string &t, size_t pos0, bool anchored, bool to_end, Memo &memo) const
  {
    const size_t n = t.size();
    std::vector<uint32_t> mark(code.size(), 0);
    uint32_t generation = 0;
    std::vector<int32_t> current, next, stack;
    bool found = false;

    const auto closure = [&](std::vector<int32_t> &list, int32_t pc0, size_t pos) {
      stack.push_back(pc0);
      while (!stack.empty()) {
        const int32_t pc = stack.back();
        stack.pop_back();
        if (mark[size_t(pc)] == generation) {
          continue;
        }
        mark[size_t(pc)] = generation;
        const Inst &inst = code[size_t(pc)];
        switch (inst.op) {
          case Op::Char:
          case Op::Any:
          case Op::Class:
            list.push_back(pc);
            break;
          case Op::Split:
            stack.push_back(inst.y);
            stack.push_back(inst.x);
            break;
          case Op::Jump:
            stack.push_back(inst.x);
            break;
          case Op::Assert:
            if (assertion_holds(inst.assertion, t, pos)) {
              stack.push_back(pc + 1);
            }
            break;
          case Op::Look:
            if (look_holds(inst, t, pos, memo)) {
              stack.push_back(pc + 1);
            }
            break;
          case Op::Match:
            if (!to_end || pos == n) {
              found = true;
            }
            break;
        }
      }
    };

    generation++;
    closure(current, entry, pos0);
    if (found) {
      return true;
    }
    for (size_t pos = pos0; pos < n; pos++) {
      const char32_t c = t[pos];
      generation++;
      next.clear();
      for (int32_t pc : current) {
        const Inst &inst = code[size_t(pc)];
        const bool ok = inst.op == Op::Char    ? inst.ch == c :
                        inst.op == Op::Any     ? c != U'\n' :
                                                 classes[size_t(inst.x)].contains(c);
        if (ok) {
          closure(next, pc + 1, pos + 1);
        }
      }
      if (!anchored) {
        closure(next, entry, pos + 1);
      }
      if (found) {
        return true;
      }
      std::swap(current, next);
      if (current.empty() && anchored) {
        return false;
      }
    }
    return false;
  }

  bool execute(std::string_view text, bool anchored, bool to_end) const
  {
    const std::u32string t = core::utf8::to_utf32(text);
    Memo memo;
    memo.results.resize(size_t(looks));
    return run(start, t, 0, anchored, to_end, memo);
  }
};

PyRegex::PyRegex(std::string_view pattern) : pattern_(pattern), program_(std::make_unique<Program>())
{
  if (!core::utf8::is_valid(pattern)) {
    throw RegexError("pattern is not valid UTF-8");
  }
  Parser parser(core::utf8::to_utf32(pattern), program_->classes);
  const std::unique_ptr<Node> root = parser.parse();
  /* Look bodies are emitted inline behind a jump; the main program starts at 0. */
  program_->start = 0;
  program_->compile(*root);
  program_->emit({Op::Match});
}

PyRegex::~PyRegex() = default;
PyRegex::PyRegex(PyRegex &&) noexcept = default;
PyRegex &PyRegex::operator=(PyRegex &&) noexcept = default;

bool PyRegex::search(std::string_view text) const
{
  return program_->execute(text, false, false);
}

bool PyRegex::match(std::string_view text) const
{
  return program_->execute(text, true, false);
}

bool PyRegex::fullmatch(std::string_view text) const
{
  return program_->execute(text, true, true);
}

bool py_regex_search(std::string_view pattern, std::string_view text)
{
  thread_local std::list<std::pair<std::string, std::shared_ptr<PyRegex>>> lru;
  thread_local std::unordered_map<std::string, decltype(lru)::iterator> index;
  const std::string key(pattern);
  auto it = index.find(key);
  if (it != index.end()) {
    lru.splice(lru.begin(), lru, it->second);
    return lru.front().second->search(text);
  }
  auto regex = std::make_shared<PyRegex>(pattern);
  lru.emplace_front(key, regex);
  index[key] = lru.begin();
  if (lru.size() > 128) {
    index.erase(lru.back().first);
    lru.pop_back();
  }
  return regex->search(text);
}

}  // namespace stk::io

// Only an explicit spoken part/whole relation can produce a pictogram.
// Never infer a ratio from unrelated numbers or arbitrary magnitudes.
export function explicitProportion(text) {
  const words = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
  ];
  const match = text
    .toLowerCase()
    .match(/\b(about\s+)?(\w+)\s+(?:of every|out of)\s+(\w+)\b/);
  if (!match) return null;
  const value = (s) => (/^\d+$/.test(s) ? Number(s) : words.indexOf(s));
  const numerator = value(match[2]);
  const denominator = value(match[3]);
  return numerator >= 0 &&
    denominator > 0 &&
    denominator <= 20 &&
    numerator <= denominator
    ? { numerator, denominator, approximate: Boolean(match[1]) }
    : null;
}

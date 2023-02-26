#!/usr/bin/env python
"""
Generates a CSV of flashcards for import into Mochi from Tatoeba sentence
pairs.
"""
import csv
import re
from collections import Counter
from dataclasses import dataclass

#
# Pair
#


@dataclass(frozen=True)
class Pair:
    eng: str
    eng_words: list[str]
    fra: str
    fra_words: list[str]

    def dump(self):
        print(f"\teng={self.eng}")
        print(f"\teng_words={self.eng_words}")
        print(f"\tfra={self.fra}")
        print(f"\tfra_words={self.fra_words}")


#
# Split sentences
#

WORD_BOUNDARY: re.Pattern[str] = re.compile(r"""[\s,\.!?"]""")


def words(line: str) -> list[str]:
    l = [w.strip() for w in re.split(WORD_BOUNDARY, line) if w.strip()]
    # Skip numbers.
    l = [w for w in l if not w.isdigit()]
    return l


#
# Parse sentences
#

FILE: str = "Sentence pairs in English-French - 2023-02-06.tsv"

WORD_LIMIT: int = 10

# List of French sentences to skip.
SKIP_LIST: list[str] = ["Eu cheguei ontem."]

def parse_sentences():
    """
    Parse sentence pairs.
    """
    pairs: list[Pair] = []
    with open(FILE, "r") as stream:
        reader = csv.reader(stream, delimiter="\t")
        for row in reader:
            eng: str = row[1].strip().lower()
            fra: str = row[3].strip().lower()
            if fra in SKIP_LIST:
                continue
            eng_words: list[str] = words(eng)
            fra_words: list[str] = words(fra)
            # Skip long sentences.
            if len(fra_words) > WORD_LIMIT:
                continue
            # Skip if there are no proper words.
            if (not eng_words) or (not fra_words):
                continue
            pair: Pair = Pair(
                eng=eng,
                eng_words=eng_words,
                fra=fra,
                fra_words=fra_words,
            )
            pairs.append(pair)
    print(f"Found {len(pairs):,} sentence pairs.")
    return pairs


#
# Language frequency tables
#


def language_frequency_table(sentences: list[list[str]]) -> Counter[str]:
    """
    Given a list of sentences (lists of words), build up a frequency table.
    """
    table: Counter[str] = Counter()
    for sentence in sentences:
        table.update(sentence)
    print(f"\tFound {len(table)} words.")
    first = most_common(table)
    last = least_common(table)
    print(f"\tMost common: '{first}' ({table[first]}).")
    print(f"\tLeast common: '{last}' ({table[last]}).")
    print(f"\tAverage English frequency: {counter_avg(table)}")
    return table


def most_common(c: Counter[str]) -> str:
    return c.most_common(1)[0][0]


def least_common(c: Counter[str]) -> str:
    min_frequency = min(c.values())
    least_common_items = [
        item for item, count in c.items() if count == min_frequency
    ]
    return least_common_items[0]


def counter_avg(c: Counter) -> float:
    total = sum(c.values())
    n = len(c)
    average_frequency = total / n
    return average_frequency


#
# Frequency cutoff
#

MOST_COMMON_WORDS_CUTOFF: float = 5000


def most_common_words(c: Counter) -> set[str]:
    return set([p[0] for p in c.most_common(MOST_COMMON_WORDS_CUTOFF)])


#
# Sorting
#


def sort_pairs(pairs: list[Pair], fra_freq: Counter[str]) -> list[Pair]:
    """
    Sort pairs from shortest and most common French words. Specifically, we
    sort by the average frequency of the words in the French sentence, divided
    by the length of the sentence, in reverse order.
    """
    return sorted(
        pairs,
        key=lambda p: avg_freq(p.fra_words, fra_freq) / len(p.fra_words),
        reverse=True,
    )


def avg_freq(words: list[str], tbl: Counter[str]) -> float:
    """
    Return the average frequency for the words.
    """
    return sum(tbl[w] for w in words) / len(words)

#
# Remove duplicates
#

def remove_duplicates(pairs: list[Pair]) -> list[Pair]:
    result: list[Pair] = []
    seen_eng: set[str] = set()
    seen_fra: set[str] = set()
    skipped: int = 0
    for pair in pairs:
        stripped_eng: str = (
            pair.eng.replace("!", "").replace(".", "").replace(",", "").strip()
        )
        stripped_fra: str = (
            pair.fra.replace("!", "").replace(".", "").replace(",", "").strip()
        )
        if stripped_eng in seen_eng:
            skipped += 1
        elif stripped_fra in seen_fra:
            skipped += 1
        else:
            result.append(pair)
            seen_eng.add(stripped_eng)
            seen_fra.add(stripped_fra)
    print(f"Skipped {skipped} sentence pairs that had the same text.")
    return pairs

#
# Build Clozes
#

CLOZE_LIMIT: int = 3


@dataclass(frozen=True)
class Cloze:
    eng: str
    fra: str


def minimize(lst, fn):
    """
    Return the value that gives the smallest value of f.
    """
    assert len(lst) > 0
    smallest_index: int = 0
    smallest_value: float = float("inf")
    for (idx, elem) in enumerate(lst):
        val: float = fn(elem)
        if val < smallest_value:
            smallest_index = idx
            smallest_value = val
    return lst[smallest_index]


def build_clozes(
    pairs: list[Pair],
    eng_freq: Counter[str],
    fra_freq: Counter[str],
    eng_common: set[str],
    fra_common: set[str],
) -> list[Cloze]:
    clozes: list[Cloze] = []
    # Track how many times we've made a cloze for each word. We don't need too
    # many clozes per word.
    cloze_count_fra: Counter[str] = Counter()
    cloze_count_eng: Counter[str] = Counter()
    skipped_limit: int = 0
    skipped_freq: int = 0
    for pair in pairs:
        # Find the rarest words in English and French.
        rarest_eng: str = minimize(pair.eng_words, lambda w: eng_freq[w])
        rarest_fra: str = minimize(pair.fra_words, lambda w: fra_freq[w])
        # Cloze the English word.
        if cloze_count_eng[rarest_eng] == CLOZE_LIMIT:
            skipped_limit += 1
        elif rarest_eng not in eng_common:
            skipped_freq += 1
        else:
            cloze_eng: Cloze = Cloze(
                eng=pair.eng.replace(rarest_eng, "{{1::" + rarest_eng + "}}"),
                fra=pair.fra,
            )
            clozes.append(cloze_eng)
            cloze_count_eng.update({rarest_eng: 1})
        # Cloze the French word.
        if cloze_count_fra[rarest_fra] == CLOZE_LIMIT:
            skipped_limit += 1
        elif rarest_fra not in fra_common:
            skipped_freq += 1
        else:
            cloze_fra: Cloze = Cloze(
                eng=pair.eng,
                fra=pair.fra.replace(rarest_fra, "{{1::" + rarest_fra + "}}"),
            )
            clozes.append(cloze_fra)
            cloze_count_fra.update({rarest_fra: 1})
    print(
        f"Skipped {skipped_limit} clozes because the word appeared too many "
        "times."
    )
    print(
        f"Skipped {skipped_freq} clozes because the word was under the "
        "frequency cutoff."
    )
    return clozes


#
# Dump clozes
#


def dump_clozes(clozes: list[Cloze]):
    print(f"Compiled {len(clozes)} clozes.")
    # Group sentences into units of 100 each.
    units: list[list[Cloze]] = group(clozes, 100)
    print(f"Dumping {len(units)} units.")
    for (unit_id, unit) in enumerate(units):
        with open(f"output/unit_{unit_id}.csv", "w") as stream:
            writer = csv.writer(
                stream,
                delimiter=",",
                quotechar='"',
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
            )
            writer.writerow(["English", "French"])
            for cloze in unit:
                writer.writerow(
                    [cloze.eng.capitalize(), cloze.fra.capitalize()]
                )


def group(lst, n):
    result = []
    for i in range(0, len(lst), n):
        result.append(lst[i : i + n])
    return result


#
# Put together
#


def main():
    # Parse sentence pairs.
    pairs: list[Pair] = parse_sentences()
    # Building frequency table.
    print("English frequency table:")
    eng_freq: Counter[str] = language_frequency_table(
        [pair.eng_words for pair in pairs]
    )
    print("French frequency table:")
    fra_freq: Counter[str] = language_frequency_table(
        [pair.fra_words for pair in pairs]
    )
    # Find the frequency cutoff.
    eng_common = most_common_words(eng_freq)
    fra_common = most_common_words(fra_freq)
    print("Sorting...")
    pairs = sort_pairs(pairs, fra_freq)
    pairs = remove_duplicates(pairs)
    # Print first and last sentences.
    print("First sentence:")
    pairs[0].dump()
    print("Last sentence:")
    pairs[-1].dump()
    # Build clozes.
    clozes: list[Cloze] = build_clozes(
        pairs, eng_freq, fra_freq, eng_common, fra_common
    )
    dump_clozes(clozes)


if __name__ == "__main__":
    main()

"""
Breaks down the existing correct/wrong/missing comparison results by the
sentence type (simple/complex/compound) of the underlying API method's
javadoc description.

This does NOT re-implement compare_specs_dataflow / compare_specs_alias.
It reads the *outputs* those functions already write to disk
(inferredCorrectSpecs.json, inferredWrongSpecs.json, inferredMissingSpecs.json)
and layers a sentence-type breakdown on top, using the description text
pulled from a DIRECTORY of per-class JSON files (one file per class, named
<FullyQualifiedClassName>.json, e.g. javadoc/benchmark-dainfer+/).

Usage:
    python compare_by_sentence_type.py

Just point the paths at the bottom to your actual files/directories.
"""

import json
import os
import re
from collections import defaultdict

import sentence_type_utils as stu


# ---------------------------------------------------------------------------
# API-doc description lookup
# ---------------------------------------------------------------------------

def extract_method_info(signature: str):
    """Same extraction logic as the original compare script: name + param count."""
    match = re.search(r"(\w+)\s*\((.*?)\)", signature)
    if match:
        name = match.group(1)
        params = match.group(2).strip()
        if not params:
            return name, 0
        return name, len([p.strip() for p in params.split(',') if p.strip()])
    return signature.strip(), 0


def load_api_doc_descriptions(api_doc_dir: str):
    """
    Parses a DIRECTORY of per-class JSON files into a lookup:
        (full_class_name_lower, method_name_lower, param_count) -> description

    One file per class, named <FullyQualifiedClassName>.json (e.g.
    android.content.ClipData.json). The full class name comes from the
    FILENAME, not the "class" field inside the JSON -- that field is only
    the simple name (e.g. "ClipData"), not enough to disambiguate.

    Matching is done on the lowercased class name because some filenames in
    this benchmark are inconsistently cased (e.g. "java.lang.charsequence.json"
    for java.lang.CharSequence, "android.content.pm.packageiteminfo.json" for
    PackageItemInfo). Nested-class filenames using "$" (Java bytecode style,
    e.g. "android.content.IntentFilter$AuthorityEntry.json") are indexed
    under BOTH the "$" and "." variants, in case your oracle/candidate specs
    use "IntentFilter.AuthorityEntry" instead.
    """
    if not os.path.isdir(api_doc_dir):
        raise NotADirectoryError(
            f"load_api_doc_descriptions expects a directory of per-class "
            f"JSON files, got: {api_doc_dir}"
        )

    lookup = {}
    skipped = 0

    for fname in sorted(os.listdir(api_doc_dir)):
        if not fname.endswith(".json"):
            continue

        full_cls_name = fname[: -len(".json")]
        fpath = os.path.join(api_doc_dir, fname)

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] skipping unreadable/invalid file {fpath}: {e}")
            skipped += 1
            continue

        methods = data.get("methods", {})

        class_name_variants = {full_cls_name.lower()}
        if "$" in full_cls_name:
            class_name_variants.add(full_cls_name.replace("$", ".").lower())

        for sig, desc in methods.items():
            name, param_count = extract_method_info(sig)
            for cls_variant in class_name_variants:
                lookup[(cls_variant, name.lower(), param_count)] = desc

    if skipped:
        print(f"[WARN] {skipped} file(s) under {api_doc_dir} could not be parsed and were skipped")

    return lookup


def get_description(lookup, full_cls_name, method_name, param_count):
    """
    Looks up a description. Class name matching is case-insensitive (see
    load_api_doc_descriptions for why). Falls back to matching by name only
    (ignoring param count) if an exact (name, count) match isn't found,
    since inferred/oracle signatures sometimes format params differently
    than the javadoc source (varargs, generics, etc).
    """
    cls_key = full_cls_name.lower()
    key = (cls_key, method_name.lower(), param_count)
    if key in lookup:
        return lookup[key]

    for (cls, name, _cnt), desc in lookup.items():
        if cls == cls_key and name == method_name.lower():
            return desc

    return None


### Added by Maryam to handle the cases of descriptions in the benchmark, such as empty description, deprecated description, etc.
def handleDescriptionCases(description: str):
    isEmpty = False
    isDeprecated = False
    if description is None:
        isEmpty = True
        return isEmpty, isDeprecated
    desc = description.strip()
    if desc == "" or len(desc) < 25 or desc.lower().startswith("same as ") or desc.lower().startswith("see "): # if the description is empty or too short, we consider it as no description, the threshold of 25 is determined based on the observation of the benchmark data, which shows that many descriptions with less than 25 characters are not informative enough to be considered as valid descriptions.
        isEmpty = True
    # replace new line characters with space
    desc = desc.replace("\n", " ")
    desc = desc.replace("\r", " ")
    # replace multiple spaces with single space
    desc = re.sub(' +', ' ', desc)
    if "deprecated" in desc.lower():
        isDeprecated = True

    return isEmpty, isDeprecated


def classify_method_verbose(lookup, full_cls_name, method_name, param_count):
    """
    Same as classify_method, but also returns the raw description text (or
    None if no method was found at all), so callers can log exactly what
    landed in "unknown" / "no_description" for manual inspection.
    """
    desc = get_description(lookup, full_cls_name, method_name, param_count)
    if desc is None:
        return "unknown", False, None

    is_empty, is_deprecated = handleDescriptionCases(desc)
    if is_empty:
        return "no_description", is_deprecated, desc

    return stu.classify_sentence_type(desc), is_deprecated, desc


def classify_method(lookup, full_cls_name, method_name, param_count):
    """
    Returns one of: "simple", "complex", "compound",
    "no_description" (method found, but description is empty/too short/a stub),
    "unknown" (method not found in the API-doc lookup at all).

    Deprecated descriptions are still classified by sentence type -- deprecation
    doesn't make a sentence ungrammatical -- but the caller can check
    is_deprecated_lookup (populated as a side effect) if it wants to report or
    exclude deprecated methods separately.
    """
    category, is_deprecated, _desc = classify_method_verbose(lookup, full_cls_name, method_name, param_count)
    return category, is_deprecated


def extract_oracle_method_keys(oracle_file, spec_type):
    """
    Extracts the exact set of (class_lower, method_name_lower, param_count)
    tuples actually REFERENCED in an oracle spec file -- as opposed to every
    method that happens to exist in a labeled class's API-doc JSON, which is
    usually a much larger, looser set (a labeled class like Collection might
    have 15+ methods documented, but the oracle might only ever reference 3
    of them).

    This reuses compare_specs.py's own signature-parsing functions
    (splitMethodFromLabelledData for dataflow, extract_method_info for
    alias) so the method set here is guaranteed to match exactly what
    compare_specs_dataflow/compare_specs_alias actually score against --
    no separate parsing logic to drift out of sync.

    spec_type must be "dataflow" or "alias" -- the two oracle files have
    different row shapes and need different per-row parsing. For "alias",
    every oracle row contributes methods from BOTH sides of the pair
    (o[1] and o[2]), since an alias spec relates two methods.
    """
    import compare_specs as cs

    oracles = cs.load_specs_from_json(oracle_file)
    keys = set()

    if spec_type == "dataflow":
        for o in oracles:
            full_cls_name = o[0]
            return_type, method_name, para_list = cs.splitMethodFromLabelledData(o[1])
            
            label = o[2]
            method = ""
            if para_list is None:
                method = f"{return_type} {method_name}()"
            else:
                if len(para_list) != 1:
                    method = f"{return_type} {method_name}({', '.join(para_list)})"
                else:
                    method = f"{return_type} {method_name}({para_list[0]})"
            
            keys.add((full_cls_name.lower(), method.lower(), label))
    elif spec_type == "alias":
        for o in oracles:
            full_cls_name = o[0]
            method1 = extract_method_info(o[1])
            method2 = extract_method_info(o[2])

            mapping = o[3]
            key = (full_cls_name, method1, method2, mapping)
            keys.add(key)
    else:
        raise ValueError(f"spec_type must be 'dataflow' or 'alias', got: {spec_type!r}")
    return keys


def count_description_categories(api_doc_dir, method_keys=None, spec_type=None, labeled_classes=None):
    """
    Iterates over EVERY method description in the API-doc directory directly
    -- independent of any candidate/oracle comparison, tp/fp/fn, or which
    model was run. This is the ground-truth corpus breakdown, not a
    by-product of scoring a particular run.

    Buckets each method's description into:
      - "no_description": empty, under 25 characters, or a stub starting
        with "same as " / "see " (same rule as handleDescriptionCases)
      - "simple" / "compound" / "complex": classify_sentence_type's result,
        for every description that ISN'T a no_description stub

    Two ways to scope which methods get counted -- pick ONE:
      - labeled_classes: restrict to methods belonging to these classes
        (coarse -- counts EVERY method in the class's API-doc JSON, even
        ones the oracle never actually references).
      - method_keys: restrict to this exact set of (class_lower,
        method_lower, param_count) tuples, e.g. from
        extract_oracle_method_keys(). This is the precise version -- only
        methods the oracle file actually mentions get counted. Recommended
        whenever you have the oracle file available, since it answers "what
        does the documentation look like for methods we actually score
        against" rather than "for the whole class."

    If both are given, method_keys takes precedence (it already implies
    class membership, since each key includes the class name).

    Returns a dict: {"no_description": N, "simple": N, "compound": N,
    "complex": N, "deprecated": N, "total_methods": N}
    """
    if not os.path.isdir(api_doc_dir):
        raise NotADirectoryError(
            f"count_description_categories expects a directory of per-class "
            f"JSON files, got: {api_doc_dir}"
        )

    counts = {"no_description": 0, "simple": 0, "compound": 0, "complex": 0, "deprecated": 0, "total_methods": 0}
    skipped_files = 0

    methods_dataset = {}

    for fname in sorted(os.listdir(api_doc_dir)):
        if not fname.endswith(".json"):
            continue

        full_cls_name = fname[: -len(".json")]
        cls_lower = full_cls_name.lower()

        fpath = os.path.join(api_doc_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] skipping unreadable/invalid file {fpath}: {e}")
            skipped_files += 1
            continue

        methods = data.get("methods", {})
        for sig, desc in methods.items():
            name, param_count = extract_method_info(sig)
            methods_dataset[(cls_lower , name.lower(),param_count)] = desc

    found = []

    if spec_type == "dataflow":
        labeled_classes = [c.lower() for c in labeled_classes]
        for o in method_keys:
            class_name = o[0]
            method_sig = o[1]
            if labeled_classes and class_name not in labeled_classes:
                print(f"[WARN] skipping method {method_sig} in class {class_name} because class is not in labeled_classes")
                continue
            if not method_sig:
                continue
            methodname, param_count = extract_method_info(method_sig)
            if methods_dataset.get((class_name.lower(), methodname.lower(), param_count)) is None:
                continue
            if (class_name.lower(), methodname.lower(), param_count) in found:
                continue
            found.append((class_name.lower(), methodname.lower(), param_count))
            desc = methods_dataset[(class_name.lower(), methodname.lower(), param_count)]

            if desc is None:
                continue
            
            is_empty, is_deprecated = handleDescriptionCases(desc)
            if is_deprecated:
                counts["deprecated"] += 1
            if is_empty:
                counts["no_description"] += 1
            else:
                cat = stu.classify_sentence_type(desc)
                counts[cat] = counts.get(cat, 0) + 1
            counts["total_methods"] += 1

    elif spec_type == "alias":
        for o in method_keys:
            class_name = o[0]
            method1 = o[1]
            method2 = o[2]

            for method in [method1, method2]:
                name, param_count = method
                if methods_dataset.get((class_name.lower(), name.lower(), param_count)) is None:
                    continue
                desc = methods_dataset[(class_name.lower(), name.lower(), param_count)]
                if (method, class_name) in found:
                    continue
                found.append((method, class_name))
                is_empty, is_deprecated = handleDescriptionCases(desc)
                if is_deprecated:
                    counts["deprecated"] += 1
                if is_empty:
                    counts["no_description"] += 1
                else:
                    cat = stu.classify_sentence_type(desc)
                    counts[cat] = counts.get(cat, 0) + 1
                counts["total_methods"] += 1

    if skipped_files:
        print(f"[WARN] {skipped_files} file(s) under {api_doc_dir} could not be parsed and were skipped")

    return counts


def print_description_category_counts(counts, title):
    total = counts["total_methods"]
    print(f"\n----- {title} (total methods: {total}) -----")
    for cat in ["no_description", "simple", "compound", "complex"]:
        n = counts.get(cat, 0)
        pct = (n / total * 100) if total > 0 else 0
        print(f"{cat:16s} {n:6d} {pct:6.1f}%")
    print(f"{'deprecated':16s} {counts.get('deprecated', 0):6d} (subset of the above, not additive)")


def diagnose_method_key_matching(api_doc_dir, method_keys):
    """
    Diagnoses why count_description_categories's total might not match the
    oracle file's own reported method/class counts. For each oracle key,
    checks how many API-doc corpus entries actually match it:

      - 0 matches ("unmatched"): the oracle references a method that
        couldn't be found in the corpus at all -- a class-name mismatch, a
        missing class file, or a signature that doesn't parse into the same
        (name, param_count) key as the corpus entry. These methods are
        silently DROPPED from count_description_categories's total, which
        makes the reported total LOWER than the oracle file's own count.

      - 1 match: clean, unambiguous match -- no issue.

      - 2+ matches ("ambiguous"): the class has multiple overloaded methods
        sharing the same name AND parameter COUNT (but, necessarily,
        different parameter TYPES, which this (class, name, param_count)
        key scheme cannot distinguish -- e.g. add(String) and add(int) both
        key to (cls, "add", 1)). ALL of them get counted by
        count_description_categories, which makes the reported total
        HIGHER than the oracle file's own count.

    Returns (unmatched_keys, ambiguous_keys, match_counts) so you can
    inspect exactly which oracle entries fall into each bucket, rather than
    only seeing the aggregate discrepancy.
    """
    if not os.path.isdir(api_doc_dir):
        raise NotADirectoryError(api_doc_dir)

    match_counts = {}
    for fname in sorted(os.listdir(api_doc_dir)):
        if not fname.endswith(".json"):
            continue
        full_cls_name = fname[: -len(".json")]
        cls_lower = full_cls_name.lower()
        fpath = os.path.join(api_doc_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        methods = data.get("methods", {})
        for sig in methods:
            name, param_count = extract_method_info(sig)
            key = (cls_lower, name.lower(), param_count)
            match_counts[key] = match_counts.get(key, 0) + 1

    unmatched_keys = sorted(k for k in method_keys if match_counts.get(k, 0) == 0)
    ambiguous_keys = sorted(k for k in method_keys if match_counts.get(k, 0) >= 2)
    clean_count = len(method_keys) - len(unmatched_keys) - len(ambiguous_keys)

    print(f"Oracle keys checked: {len(method_keys)}")
    print(f"  clean, unambiguous matches: {clean_count}")
    print(f"  unmatched (0 corpus entries -- likely UNDERcounts totals): {len(unmatched_keys)}")
    print(f"  ambiguous (2+ corpus entries -- overloaded name+paramcount, likely OVERcounts totals): {len(ambiguous_keys)}")
    if unmatched_keys:
        print(f"\n  first few unmatched keys: {unmatched_keys[:10]}")
    if ambiguous_keys:
        print(f"\n  first few ambiguous keys (and how many corpus entries each matched):")
        for k in ambiguous_keys[:10]:
            print(f"    {k} -> {match_counts[k]} entries")

    return unmatched_keys, ambiguous_keys, match_counts


def diagnose_class_name_conventions(api_doc_dir, oracle_file, spec_type):
    """
    Checks whether the oracle file's class-name convention actually matches
    the API-doc corpus's convention (derived from filenames) -- e.g. the
    oracle using a bare simple/partial name like "Uri$Builder" while the
    corpus expects a fully-qualified name like "android.net.Uri$Builder".

    This is a DIFFERENT failure mode from diagnose_method_key_matching:
    that function assumes the class name itself resolves correctly and
    only checks whether the specific METHOD within that class matches.
    This function checks the class name resolution itself, which is a
    precondition for anything else to work -- if the class name never
    matches, every method in it is silently dropped regardless of whether
    the method-level signature is otherwise fine.

    Prints a sample of oracle class names that DO resolve to a corpus
    filename and a sample that DON'T, so you can visually compare the
    naming conventions side by side rather than guess.
    """
    import compare_specs as cs

    oracles = cs.load_specs_from_json(oracle_file)
    oracle_classes = sorted({o[0] for o in oracles})

    corpus_classes_lower = set()
    for fname in os.listdir(api_doc_dir):
        if fname.endswith(".json"):
            corpus_classes_lower.add(fname[: -len(".json")].lower())

    matched = [c for c in oracle_classes if c.lower() in corpus_classes_lower]
    unmatched = [c for c in oracle_classes if c.lower() not in corpus_classes_lower]

    print(f"=== Class-name convention check ({spec_type} oracle vs. corpus filenames) ===")
    print(f"Unique classes referenced in oracle: {len(oracle_classes)}")
    print(f"  resolve to a corpus filename:      {len(matched)}")
    print(f"  do NOT resolve to any filename:     {len(unmatched)}")
    if matched:
        print(f"\n  sample MATCHED oracle class names: {matched[:5]}")
    if unmatched:
        print(f"\n  sample UNMATCHED oracle class names: {unmatched[:10]}")
        print(f"  (compare these against your actual filenames under {api_doc_dir} --")
        print(f"   if the unmatched ones are bare/simple names like 'Uri$Builder' while")
        print(f"   your filenames are fully-qualified like 'android.net.Uri$Builder.json',")
        print(f"   that convention mismatch is why they're being silently dropped.)")

    return matched, unmatched


# ---------------------------------------------------------------------------
# Parsing helpers for the two different key shapes produced by the
# original compare_specs_dataflow / compare_specs_alias functions
# ---------------------------------------------------------------------------

def parse_dataflow_method_str(method_str: str):
    """
    Dataflow keys look like: (full_cls_name, "returntype methodname(params)", label)
    already lowercased by the original script. Extract name + param count.
    """
    m = re.search(r"(\w+)\s*\((.*?)\)", method_str)
    if not m:
        return method_str, 0
    name = m.group(1)
    params = m.group(2).strip()
    if not params:
        return name, 0
    return name, len([p for p in params.split(',') if p.strip()])


def load_json_list(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Dataflow: bucket by single-method sentence type
# ---------------------------------------------------------------------------

def bucket_dataflow_by_sentence_type(correct, wrong, missing, lookup, unknown_log=None):
    """
    unknown_log, if given a list, gets one dict appended per spec whose
    method landed in "unknown" or "no_description", with the class/method
    and whatever description text (if any) was found -- so you can inspect
    exactly what's falling into those buckets.
    """
    buckets = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "deprecated": 0})

    def tally(key, count_field, source):
        cls, method_str, _label = key
        name, count = parse_dataflow_method_str(method_str)
        cat, is_deprecated, desc = classify_method_verbose(lookup, cls, name, count)
        buckets[cat][count_field] += 1
        if is_deprecated:
            buckets[cat]["deprecated"] += 1
        if unknown_log is not None and cat in ("unknown", "no_description"):
            unknown_log.append({
                "source": source,
                "class": cls,
                "method_name": name,
                "param_count": count,
                "category": cat,
                "description": desc if desc is not None else "",
            })

    for key in correct:
        tally(key, "tp", "correct")
    for key in wrong:
        tally(key, "fp", "wrong")
    for key in missing:
        tally(key, "fn", "missing")

    return buckets


# ---------------------------------------------------------------------------
# Alias: bucket by method-PAIR sentence type, e.g. "simple-complex"
# ---------------------------------------------------------------------------

def bucket_alias_by_sentence_pair_type(correct, wrong, missing, lookup, unknown_log=None):
    """
    Alias keys look like: (full_cls_name, [name, count], [name, count], mapping)
    -- note: json.dump/json.load turns the original tuples into lists.

    unknown_log works the same as in bucket_dataflow_by_sentence_type, but
    since each alias spec involves TWO methods, either or both may land in
    "unknown"/"no_description" -- each gets its own logged row (tagged
    method1/method2) rather than collapsing them into one row per spec.
    """
    buckets = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "deprecated": 0})

    def classify_and_maybe_log(cls, m, method_slot, source):
        name, count = m[0], m[1]
        cat, is_deprecated, desc = classify_method_verbose(lookup, cls, name, count)
        if unknown_log is not None and cat in ("unknown", "no_description"):
            unknown_log.append({
                "source": source,
                "method_slot": method_slot,
                "class": cls,
                "method_name": name,
                "param_count": count,
                "category": cat,
                "description": desc if desc is not None else "",
            })
        return cat, is_deprecated

    def pair_category(cls, m1, m2, source):
        cat1, dep1 = classify_and_maybe_log(cls, m1, "method1", source)
        cat2, dep2 = classify_and_maybe_log(cls, m2, "method2", source)
        return f"{cat1}-{cat2}", (dep1 or dep2)

    def tally(key, count_field, source):
        cls, m1, m2, _mapping = key
        cat, is_deprecated = pair_category(cls, m1, m2, source)
        buckets[cat][count_field] += 1
        if is_deprecated:
            buckets[cat]["deprecated"] += 1

    for key in correct:
        tally(key, "tp", "correct")
    for key in wrong:
        tally(key, "fp", "wrong")
    # NOTE: with the compare_specs.py fix (missing is now populated in
    # compare_specs_alias directly), this loop is no longer a no-op --
    # you can drop recompute_alias_missing() below if you're regenerating
    # inferredMissingSpecs.json with the updated compare_specs.py.
    for key in missing:
        tally(key, "fn", "missing")

    return buckets


def recompute_alias_missing(candidate_file, oracle_file, labeled_classes_file):
    """
    Mirrors what compare_specs_dataflow does for `missing` (oracle_index keys
    not found in correct), applied to the alias format. This exists because
    the original compare_specs_alias never fills `missing`, which means you
    can't get per-category recall for alias specs without it. Wire this in
    if you want that.
    """
    import compare_specs as cs  # the user's original module

    candidates = cs.load_specs_from_json(candidate_file)
    oracles = cs.load_specs_from_json(oracle_file)
    labeled_classes = cs.load_labeled_classes(labeled_classes_file)

    oracle_index = {}
    for o in oracles:
        full_cls_name = o[0]
        if full_cls_name not in labeled_classes:
            continue
        method1 = cs.extract_method_info(o[1])
        method2 = cs.extract_method_info(o[2])
        mapping = o[3]
        oracle_index[(full_cls_name, method1, method2, mapping)] = True

    correct_keys = set()
    for spec in candidates:
        full_cls_name = spec[1]
        if full_cls_name not in labeled_classes:
            continue
        method1 = cs.extract_method_info(spec[2])
        method2 = cs.extract_method_info(spec[3])
        mapping = spec[6]
        key = (full_cls_name, method1, method2, mapping)
        if key in oracle_index:
            correct_keys.add(key)

    missing = [list(k) for k in oracle_index if k not in correct_keys]
    return missing


def print_single_category_metrics(buckets, title):
    print(f"\n----- {title} -----")
    
    real_cats = ["simple", "compound", "complex"]
    total_tp = sum(buckets[c]["tp"] for c in real_cats if c in buckets)
    total_fp = sum(buckets[c]["fp"] for c in real_cats if c in buckets)
    total_fn = sum(buckets[c]["fn"] for c in real_cats if c in buckets)
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    recall    = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    print(f"{'OVERALL':15s} | TP={total_tp:4d} FP={total_fp:4d} FN={total_fn:4d} | "
          f"Precision={precision:.4f} Recall={recall:.4f} F1={f1:.4f}")
    print()

    priority = {"unknown": 1, "no_description": 1}
    categories = sorted(buckets.keys(), key=lambda c: (priority.get(c, 0), c))
    for cat in categories:
        tp = buckets[cat]["tp"]
        fp = buckets[cat]["fp"]
        fn = buckets[cat]["fn"]
        deprecated = buckets[cat]["deprecated"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(f"{cat:15s} | TP={tp:4d} FP={fp:4d} FN={fn:4d} (deprecated={deprecated:3d}) | "
              f"Precision={precision:.4f} Recall={recall:.4f} F1={f1:.4f}")


def print_pair_category_metrics(buckets, title):
    print(f"\n----- {title} -----")

    real_cats = [c for c in buckets if not any(
        part in ("unknown", "no_description") for part in c.split("-")
    )]
    total_tp = sum(buckets[c]["tp"] for c in real_cats)
    total_fp = sum(buckets[c]["fp"] for c in real_cats)
    total_fn = sum(buckets[c]["fn"] for c in real_cats)
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    recall    = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    print(f"{'OVERALL':35s} | TP={total_tp:4d} FP={total_fp:4d} FN={total_fn:4d} | "
          f"Precision={precision:.4f} Recall={recall:.4f} F1={f1:.4f}")
    print()

    categories = sorted(buckets.keys())
    for cat in categories:
        tp = buckets[cat]["tp"]
        fp = buckets[cat]["fp"]
        fn = buckets[cat]["fn"]
        deprecated = buckets[cat]["deprecated"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        line = f"{cat:35s} | TP={tp:4d} FP={fp:4d} FN={fn:4d} (deprecated={deprecated:3d}) | Precision={precision:.4f}"
        if tp + fn > 0:
            recall = tp / (tp + fn)
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            line += f" Recall={recall:.4f} F1={f1:.4f}"
        else:
            line += " Recall=n/a"
        print(line)


def write_unknown_log_csv(path, entries, dedup=True):
    """
    Writes the collected unknown/no_description entries to a CSV for manual
    inspection. Set dedup=True (default) to collapse repeated rows for the
    same (class, method_name, param_count, category) -- useful for alias
    logs where the same method can show up across many pair specs.
    """
    import csv as _csv

    if dedup:
        seen = {}
        for e in entries:
            key = (e["class"], e["method_name"], e["param_count"], e["category"])
            if key not in seen:
                seen[key] = e
        rows = list(seen.values())
    else:
        rows = entries

    fieldnames = ["source", "method_slot", "class", "method_name", "param_count", "category", "description"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[INFO] wrote {len(rows)} unknown/no_description rows to {path}")


import spacy
import re

nlp = spacy.load("en_core_web_sm")

conjunction_groups = {
        "cause/effect": ["because", "since", "as", "so that", "in order that"],
        "time": ["after", "before", "when", "while", "until", "as soon as"],
        "condition": ["if", "unless", "whether", "provided that"],
        "contrast/concession": ["although", "though", "even though", "whereas"],
        "purpose": ["so that", "in order that"],
        "comparison": ["than", "as"]
    }

#---------------------------------------------------
# Check the location of the conjunction in the sentence
#---------------------------------------------------
def check_conjunction_location(doc, start_index, conj_token):
    if conj_token.i == start_index:
        return 1
    elif conj_token.i == len(doc) - 1:
        return 3
    elif 0 < conj_token.i < len(doc) - 1:
        return 2
    return 0

#----------------------------------------------------
# Check if a sentence is a simple sentence
#--------------------------------------------------
def is_simple_sentence(doc):
    """ Check if a clause is a simple sentence."""
    has_cc = any(token.dep_ == "cc" for token in doc)  # Check for coordinating conjunctions
    has_mark = any(token.dep_ == "mark" for token in doc)  # Check for subordinating conjunctions
    return not has_cc and not has_mark  # Simple sentence has no cc or mark

def remove_parentheses(span):
    """Remove parentheses and their content from a span."""
    text = span.text
    stack = []
    result = []
    skip = 0

    for char in text:
        if char == '(':
            stack.append(char)
            skip += 1
        elif char == ')':
            if stack:
                stack.pop()
                skip -= 1
        else:
            if skip == 0:
                result.append(char)

    return nlp(''.join(result).strip())


def retrieve_comma_clauses(doc, start_index):
    clauses = []
    for token in doc:
        if token.text == ',':
            clause = doc[start_index:token.i].text.strip()
            # check if the clause has a verb
            if any(t.pos_ == "VERB" for t in nlp(clause)):
                clauses.append(clause)
                start_index = token.i + 1

    return clauses

#---------------------------------------------------
# Determine conjunction type based on its text
#---------------------------------------------------
def determine_conjunction_type(conj_text):
    for group, conjunctions in conjunction_groups.items():
        if conj_text.lower() in conjunctions:
            return group
    return "unknown"

def find_negated_verb(clause):
    doc = nlp(clause)
    for token in doc:
        if token.dep_ == "neg" and token.head.pos_ == "VERB":
            return True
    return False

#---------------------------------------------------
# Get relevant clauses based on conjunction group
#---------------------------------------------------
def get_relevant_clauses(conjunction_group, clause_1, clause_2):
    if conjunction_group in ["cause/effect", "condition", "contrast/concession", "purpose", "comparison"]:
        return clause_1
    elif conjunction_group == "time":
        return (clause_1, clause_2)
    return None

#---------------------------------------------------
# Retrieve clauses from the document based on conjunction position
#---------------------------------------------------
def retrieve_clauses_cc(doc, start_index, conj_token):
    pos = check_conjunction_location(doc, start_index, conj_token)
    if pos == 1:
        clause_1 = doc[start_index:conj_token.i + 1].text.strip()
        clause_2 = doc[conj_token.i + 1:].text.strip()
        if clause_1 and clause_2:
            clause_2_has_verb = any(t.pos_ == "VERB" for t in doc[conj_token.i + 1:])
            if clause_2_has_verb:
                return clause_1, clause_2
            else:
                return doc[start_index:].text.strip(),""
    elif pos == 2:
        clause_1 = doc[start_index:conj_token.i].text.strip()
        clause_2 = doc[conj_token.i:].text.strip()
        if clause_1 and clause_2:
            clause_1_has_verb = any(t.pos_ == "VERB" for t in doc[start_index:conj_token.i])
            clause_2_has_verb = any(t.pos_ == "VERB" for t in doc[conj_token.i:])
            if clause_1_has_verb and clause_2_has_verb:
                return clause_2, clause_1
            else:
                return doc[start_index:].text.strip(),""
    return "",""

def split_by_semicolon(sentence):
    """
    Split a sentence by semicolons (;).
    
    Args:
        sentence (str): The input sentence.
    
    Returns:
        list: A list of parts split by semicolons.
    """
    parts = sentence.split(";")
    return [p.strip() for p in parts if p.strip()]


def process_sentence_for_independent(sent):
    """
    Process a single sentence to extract only independent clauses.
    
    Args:
        sent (spacy.tokens.Span): A spaCy Span object representing a sentence.
    
    Returns:
        list: A list of independent simple sentences.
    """
    nlp = spacy.load("en_core_web_sm")
    independent_sentences = []
    verbs = []

    # Remove parentheses and their content
    sent_text = sent.text
    sent_text = re.sub(r'\([^)]*\)', '', sent_text)  # Remove ( ... )
    sent_text = sent_text.strip()
    doc = nlp(sent.text) # Create a new doc from cleaned text

    # Track tokens that are part of dependent clauses
    dependent_token_indices = set()

    # Step 1: Find all mark tokens and their dependent clause tokens
    for token in doc:
        if token.dep_ in ("mark", "relcl"):
            # Get the subtree of the clause head
            # For 'mark', the clause head is usually a verb
            # if the clause head does not have a verb, we consider the head itself
            target_node = token.head if token.dep_ == "mark" else token
            if not any(t.pos_ == "VERB" for t in target_node.subtree):
                target_node = token.head

            for t in target_node.subtree:
                dependent_token_indices.add(t.i)

    # Step 2: Extract independent tokens (not part of any dependent clause)
    independent_tokens = [t for t in doc if t.i not in dependent_token_indices]

    # Step 3: Build the independent clause
    independent_clause = " ".join([t.text for t in independent_tokens]).strip()

    # Step 4: Clean up punctuation and extra spaces
    independent_clause = clean_clause(independent_clause)

    # Step 5: Split by cc tokens (coordinating conjunctions)
    if independent_clause:
        split_clauses = split_by_cc(independent_clause)
        verbs = retrieve_verbs_from_clauses(split_clauses)
        independent_sentences.extend(split_clauses)

    return independent_sentences, verbs

def retrieve_verbs_from_clauses(clauses):
    verbs = []
    for clause in clauses:
        doc = nlp(clause)
        for token in doc:
            if token.pos_ == "VERB":
                verbs.append(token.lemma_)
    return verbs

def split_by_cc(sentence):
    """
    Split a sentence by coordinating conjunctions (cc).
    
    Args:
        sentence (str): The input sentence.
    
    Returns:
        list: A list of clauses split by coordinating conjunctions.
    """
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(sentence)
    clauses = []
    start_index = 0
    for token in doc:
            if token.dep_ == "cc":
                # Check if the right clause (after cc) contains a verb
                right_span = doc[token.i + 1:]
                if any(t.pos_ == "VERB" for t in right_span):
                    # Split: add left and right as separate clauses (if left has a verb)
                    left_span = doc[start_index:token.i]
                    if any(t.pos_ == "VERB" for t in left_span):
                        clauses.append(left_span.text.strip())
                    if any(t.pos_ == "VERB" for t in right_span):
                        clauses.append(right_span.text.strip())
                    print("left: " + left_span.text.strip())
                    print("right: " + right_span.text.strip())
                    return clauses  # Stop after first split
                else:
                    # Do not split: keep the whole clause with the phrase after cc
                    whole_span = doc[start_index:]
                    print("whole: " + whole_span.text.strip())
                    clauses.append(whole_span.text.strip())
                    return clauses  # Stop after first cc

    # If no cc or no split, return the whole sentence
    clauses.append(doc.text.strip())
    return clauses

    # If no cc tokens found, return the original sentence
    #if not clauses:
    #    clauses.append(sentence.strip())

    #return clauses


def clean_clause(clause):
    """
    Clean up a clause by removing leading/trailing punctuation and extra spaces.
    
    Args:
        clause (str): The input clause.
    
    Returns:
        str: The cleaned clause.
    """
    # Remove leading/trailing whitespace
    clause = clause.strip()

    # Remove leading punctuation (comma, period, etc.)
    while clause and clause[0] in ",.;:!?":
        clause = clause[1:].strip()

    # Remove trailing punctuation (except period)
    while clause and clause[-1] in ",.;:!?":
        clause = clause[:-1].strip()

    return clause

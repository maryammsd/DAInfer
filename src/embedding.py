import torch
import time
import nltk
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer,util 
from transformers import AutoTokenizer, AutoModel, RobertaTokenizer, RobertaModel, AutoModelForMaskedLM
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial.distance import euclidean, pdist, squareform
from nltk.tokenize import sent_tokenize
import os
import json
import spacy
import simplify
import concurrent.futures
import config
os.environ["CUDA_LAUNCH_BLOCKING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Define targets once
TARGET_OPS = ["set", "get", "insert", "remove"]
TARGET_PHRASES = [
    "sets value of something.", 
    "gets value of something.", 
    "inserts something into a collection.", 
    "removes something from a collection."
]

nlp = spacy.load("en_core_web_sm", disable=["ner"])

# Encode once and move to GPU (this takes ~0.01 seconds)
GLOBAL_TARGET_EMBS = None 

def initialize_targets(model):
    global GLOBAL_TARGET_EMBS
    # convert_to_tensor=True puts it on GPU immediately for matrix math
    GLOBAL_TARGET_EMBS = model.encode(TARGET_PHRASES, convert_to_tensor=True)

def batch_retrieve_memory_operations(model, api_methods_list):
    """
    api_methods_list: A list of dicts/objects containing 
    {'className': ..., 'methodSig': ..., 'methodDoc': ...}
    """
    # 1. Extract all documentation strings into one list, api_methods_list is in the form of a list of dicts of (className, sig1, description1)
    all_docs = []
    all_verbs = []
    sentence_to_method_map = {}
    count = 0
    before = time.perf_counter()
    nlp = spacy.load("en_core_web_sm", disable=["ner"])
    processed_data = []

    descriptions = [item[3] for item in api_methods_list] 

    # Use ProcessPoolExecutor to run the logic in parallel across all CPU cores
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # map() maintains the order of api_methods_list
        results = list(executor.map(get_independent_sentences, descriptions))

    # 3. Map the results back to your metadata
    for i, (packageName, className, sig1, description2) in enumerate(api_methods_list):
        sentences, verbs = results[i]
        
        count += len(sentences)
        for verb in verbs:
            if verb not in all_verbs:
                all_verbs.append(verb)
                
        for sentence in sentences:
            all_docs.append(sentence)
            sentence_to_method_map[sentence] = (packageName, className, sig1)
    after = time.perf_counter()
    config.SENTENCEE_PROCESSING_TIME += (after - before)
    config.number_of_sentences += count

    print(f"Starting batch encoding for {len(all_docs)} methods...")
    start_time = time.perf_counter()

    # 2. BATCH ENCODE: This is the 'Secret Sauce'
    # By using a large batch_size, the GPU processes 128 items at once
    doc_embeddings = model.encode(all_docs, batch_size=128, convert_to_tensor=True)

    # 3. MATRIX MULTIPLICATION: Compare all docs to all 4 targets at once
    # This replaces the similarity_function loops entirely
    # Shape: [1045, 4]
    cosine_scores = util.cos_sim(doc_embeddings, GLOBAL_TARGET_EMBS)
    
    end_time = time.perf_counter()
    
    # Calculate Real Throughput
    total_time = end_time - start_time
    config.EMBEDTime += total_time
    throughput = len(all_docs) / total_time
    print(f"DONE. Throughput: {throughput:.2f} items/sec (Total Time: {total_time:.4f}s)")
    print(f"number of sentences {config.number_of_sentences}")
    print(f" ToTal sentence processing time: {config.SENTENCEE_PROCESSING_TIME:.4f}s")

    # 4. Process Results (Map back to your original format)
    final_results = []
    for i, scores in enumerate(cosine_scores):
        packageName, className, sig1 = sentence_to_method_map[all_docs[i]]
        method_key = (packageName, className, sig1)
        method_result = {}
        if method_result.get(method_key) is None:
            method_result[method_key] = {}
            op_results = normalize_scores(scores, isMax=False, sentence=all_docs[i])
            for op, score in op_results:
                method_result[method_key][op] = float(round(score, 2))
                
        else:
            # Update existing entry if needed
            new_score = float(scores)
            new_results = normalize_scores(new_score, isMax=False, sentence=all_docs[i])
            for op, score in new_results:
                if method_result[method_key].get(op) is None or score > method_result[method_key][op]:
                    method_result[method_key][op] = float(round(score, 2))
        final_results.append(method_result)
          
    return final_results, all_verbs


def normalize_scores(scores, isMax, sentence):
    results = []
    if isMax:
        max_ops, max_score = find_max_similarity_operation(scores, is_max=True)
        for op in max_ops:
            results.append((op, max_score))
            print(f"   → Sentence: '{sentence}' | Predicted Operation: '{max_ops}' (Score: {max_score:.2f})")
        return results
    max_ops, max_score = find_max_similarity_operation(scores, is_max=False)
    for op in max_ops:
        results.append((op, max_score))
    
    return results
# --------------------------------------------------
# Similarity function
# --------------------------------------------------
def similarity_function(vec1, vec2, method):
    if method == "cosine":
        return cosine_similarity(vec1, vec2)[0][0]
    elif method == "euclidean":
        distance = np.linalg.norm(vec1 - vec2)
        return distance  # Convert to similarity
    else:
        raise ValueError(f"Unknown similarity method: {method}")


def run_embedding_models():

    if config.EMBEDDING_MODEL == "sentencebert":
        return load_sentencebert_model()
    elif config.EMBEDDING_MODEL == "e5":
        return load_e5_model()
    return None  

# ------------------------------------------------------------------
# LOAD MODEL FUNCTION - SentenceBERT
# ------------------------------------------------------------------
def load_sentencebert_model(model_name="all-MiniLM-L6-v2"):
    # other models for sentence embedding:
    # "all-MiniLM-L6-v2"  Smaller, faster (fewer layers/dimensions) for speed.
    # "all-mpnet-base-v2" Uses MPNet (better performance).
    # 
    model_name = "all-mpnet-base-v2"  # Replace with your model name 
    model = SentenceTransformer(model_name, device="cuda")  # Force the model to load on the CPU
    return model


#-------------------------------------------------------------------
#  
#-------------------------------------------------------------------
def load_e5_model(model_name="intfloat/e5-base"):
    # E5 models for sentence embedding:
    # "intfloat/e5-small"  Smaller, faster (fewer layers/dimensions) for speed.
    # "intfloat/e5-large"  Larger, better performance.
    # "intfloat/e5-base"   Balanced option.
    model_name = "intfloat/e5-large"
    model = SentenceTransformer(model_name, device="cuda")  # Force the model to load on the CPU
    return model

# ------------------------------------------------------------------
#  LOAD MODEL FUNCTION - CodeBert
# ------------------------------------------------------------------
def load_model_codebert(model_name="microsoft/codebert-base"):
    model_name = "microsoft/codebert-base"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name, output_hidden_states=True)
    model.eval()
    return tokenizer, model

def load_model_codebert_MLM(model_name="microsoft/codebert-base"):
    model_name = "microsoft/codebert-base"
    tokenizer = RobertaTokenizer.from_pretrained(model_name)
    model = AutoModelForMaskedLM.from_pretrained(model_name)
    model.eval()
    return tokenizer, model

#--------------------------------------------------
# Split description into simple sentences
#--------------------------------------------------
def get_independent_sentences(sentence):
    """
    Extract only independent sentences from a compound, complex, or compound-complex sentence.
    Removes dependent clauses (introduced by mark tokens) and splits by cc tokens.
    
    Args:
        sentence (str): The input sentence to analyze.
    Returns:
        list: A list of independent simple sentences.
    """
    global nlp
     # Step 1: Split by semicolons first
    semicolon_parts = simplify.split_by_semicolon(sentence)
    
    independent_sentences = []
    verbs = []

    for part in semicolon_parts:
        # Step 2: Process each part using the loaded nlp
        doc = nlp(part)

        for sent in doc.sents:
            processed, new_verbs = simplify.process_sentence_for_independent(sent)
            independent_sentences.extend(processed)
            verbs.extend(new_verbs)

    # Post-processing
    prefix = "this method is used to "
    cleaned = [
        s[len(prefix):].strip() if s.lower().startswith(prefix) else s.strip()
        for s in independent_sentences if s.strip()
    ]
    
    # Remove duplicates while preserving order
    unique_sentences = list(dict.fromkeys(cleaned))
    return unique_sentences, verbs

    nlp = spacy.load("en_core_web_sm")
    doc = nlp(sentence)
    independent_sentences = []
    verbs = []

    # Step 1: Split by semicolons first
    semicolon_parts = simplify.split_by_semicolon(sentence)

    for part in semicolon_parts:
        # Step 2: Process each part using spaCy
        doc = nlp(part)

        for sent in doc.sents:
            new_verbs = []
            processed, new_verbs = simplify.process_sentence_for_independent(sent)
            independent_sentences.extend(processed)
            verbs.extend(new_verbs)

    # Remove duplicates and empty strings
    independent_sentences = [s.strip() for s in independent_sentences if s.strip()]
    # remove "This method is used to " from the beginning of sentences
    independent_sentences = [s[23:].strip() if s.lower().startswith("this method is used to ") else s for s in independent_sentences]
    print(f" Independent sentences extracted: {independent_sentences} ")
    independent_sentences = list(dict.fromkeys(independent_sentences))  # Remove duplicates while preserving order

    return independent_sentences,verbs  
  
# --------------------------------------------------
# Get similarity score of verbs with target operations
# --------------------------------------------------
def get_verb_similarity_scores(model, total_verbs, target_operations, description):
    # get vector of target operations
    # split a description into sentences
    _, verbs = get_independent_sentences(description)
    current_verbs = []

    for verb in verbs:
        if verb not in total_verbs:
            total_verbs.append(verb)
            current_verbs.append(verb)
        
    target_embs = {op: model.encode(phrase) for op, phrase in target_operations.items()}
    verbs = []

    for verb in current_verbs:
        for op, phrase in target_operations.items():
            verb_emb = model.encode(verb)
            op_emb = target_embs[op]
            sim = similarity_function(verb_emb.reshape(1, -1), op_emb.reshape(1, -1), method="cosine")
            print(f"   → Verb: '{verb}' | Operation: '{op}' | Similarity Score: {sim:.4f}")
            with open("../data/output/verbs.txt", "a") as f:
                f.write(f"verb1: {verb}, verb2: {op}, score: {round(sim, 4)} \n")
    return total_verbs
   

#--------------------------------------------------
# Predict operation given description - SentenceBERT
# --------------------------------------------------
def predict_operation_sentencebert(model, description, target_operations):
    
    # split a description into sentences
    sentences, verbs = get_independent_sentences(description)

    start = time.perf_counter()

    # Encode each sentence separately
    sentence_embeddings = model.encode(sentences)

    target_embs = {op: model.encode(phrase) for op, phrase in target_operations.items()}
    target_keys = list(target_operations.keys())
    # Add at line 393

    # If it's already a numpy array, use it directly
    if isinstance(sentence_embeddings, (list, np.ndarray)):
        sentence_embeddings = sentence_embeddings  # No extraction needed
    elif isinstance(sentence_embeddings, dict):
        sentence_embeddings = sentence_embeddings['embeddings']

    results = {}
    for i, sentence_emb in enumerate(sentence_embeddings):
        # Use matrix multiplication for all similarities at once
        # This is much faster than looping through 4 vectors manually
        sim_scores = {}
        for op in target_keys:
            value = target_embs[op]
            print(f" Type of target_emb: {type(value)} for key {op}")
            score = similarity_function(value.reshape(1, -1), sentence_emb.reshape(1, -1), method="cosine")
            print(f"   → Similarity score for operation '{op}': {score:.4f}")
            # get floating point with 3 decimal points and 3 floating points, like for 1.33332424, we should get 1.333
            sim_scores[op] = round(float(score), 2)
            with open("../data/results/memory_operation_results.txt", "a") as f:
                f.write(f"sentence: {sentences[i]} with score {sim_scores[op]} for op {op} \n")

        # Find operation with max value in sim_scores, if there is more than one max, choose all of them
        # Find the distance between the scores and choose the highest ones close to the max score
        isMax = False
        if isMax:
            max_ops, max_score = find_max_similarity_operation(sim_scores, is_max=True)
            for op in max_ops:
                results[sentences[i]] = (op, max_score)
            
            print(f"   → Sentence: '{sentences[i]}' | Predicted Operation: '{max_ops}' (Score: {max_score:.2f})")
        else:
            max_ops, max_score = find_max_similarity_operation(sim_scores, is_max=False)
            for op in max_ops:
                results[sentences[i]] = (op, max_score)

    end = time.perf_counter()
    
    dim = model.get_sentence_embedding_dimension()
    config.time_embedding_model += (end - start)
    config.count_embedding_model += 1
    config.vector_shape = (1, dim)
    config.memory_latency += (dim * 4) / (1024 * 1024 * 1024)  # in seconds, assuming float32 (4 bytes)
        
    # FIX 3: Memory Size in MB (usually more readable than GB for single vectors)
    vector_size_bytes = dim * 4
    config.memory_usage_mb += (vector_size_bytes / (1024 * 1024)) 

    # Map back to labels
    final_results = {}
    for sent_emb, (op, sim) in results.items():
        print(f"Processing sentence embedding result: {sent_emb} -> ({op}, {sim})")
        if op in final_results:
            if sim > final_results[op]:
                final_results[op] = sim
        else:
            final_results[op] = sim

    # Sort the final results
    sorted_final_results = sorted(final_results.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_final_results) 


# --------------------------------------------------
# Find the max similarity operation from the scores
# --------------------------------------------------
def find_max_similarity_operation(sim_scores, is_max):
    if is_max:
        max_score = max(sim_scores.values())
        max_ops = [op for op, score in sim_scores.items() if score == max_score]
        return max_ops, max_score
    else:
        max_score = max(sim_scores.values())
        # 2. Get all operations within the threshold of the max
        close_to_max = [op for op, score in sim_scores.items() if abs(max_score - score) <= 0.003]
        print(f"   → Operations close to max score ({max_score:.2f}): {close_to_max}")
        return close_to_max, max_score


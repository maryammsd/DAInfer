import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import re
from collections import defaultdict


def read_verb_scores(filepath):
    """Read verb similarity scores from file."""
    scores = defaultdict(dict)
    
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            match = re.match(r'verb1:\s*(\S+),\s*verb2:\s*(\S+),\s*score:\s*([-\d.]+)', line)
            if match:
                verb1 = match.group(1)
                verb2 = match.group(2)
                score = float(match.group(3))
                scores[verb1][verb2] = score
    
    return scores


def create_heatmap_swapped(filepath, output_file='verb_heatmap_swapped.png'):
    """
    Create heatmap with:
    - X-axis: Verbs (verb1)
    - Y-axis: Operations (set, get, insert, remove)
    """
    # Read scores
    scores = read_verb_scores(filepath)
    
    # Define axes
    verb_list = sorted(scores.keys())  # X-axis (columns)
    operation_list = ["read", "write", "insert", "remove"]  # Y-axis (rows)
    
    # Create matrix: rows=operations, cols=verbs
    # This is TRANSPOSED from before
    similarity_matrix = np.zeros((len(operation_list), len(verb_list)))
    
    for j, verb in enumerate(verb_list):  # columns
        for i, op in enumerate(operation_list):  # rows
            if op in scores[verb]:
                similarity_matrix[i, j] = scores[verb][op]
    
    # Create heatmap
    fig_width = max(20, len(verb_list) * 0.4)
    plt.figure(figsize=(fig_width, 6))
    
    sns.heatmap(
        similarity_matrix,
        xticklabels=verb_list,      # Verbs on X-axis
        yticklabels=operation_list,  # Operations on Y-axis
        annot=True,
        fmt='.2f',
        cmap='RdYlGn',
        center=0.2,
        vmin=-0.1,
        vmax=0.6,
        linewidths=0.5,
        annot_kws={"size": 6}
    )
    
    plt.title('Verb to Operation Similarity Heatmap', fontsize=14)
    plt.xlabel('Extracted Verbs', fontsize=12)
    plt.ylabel('Target Operations', fontsize=12)
    
    # Rotate x-axis labels for readability
    plt.xticks(rotation=90, ha='center', fontsize=8)
    plt.yticks(rotation=0, fontsize=10)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.show()
    
    print(f"Heatmap saved to: {output_file}")
    
    return similarity_matrix, verb_list, operation_list


def create_filtered_heatmap_swapped(filepath, min_score=0.25, output_file='verb_heatmap_filtered_swapped.png'):
    """
    Create heatmap with only high-scoring verbs.
    - X-axis: Filtered verbs
    - Y-axis: Operations
    """
    scores = read_verb_scores(filepath)
    operation_list = ["set", "get", "insert", "remove"]
    
    # Filter verbs with at least one score >= min_score
    filtered_verbs = []
    for verb, op_scores in scores.items():
        max_score = max(op_scores.values())
        if max_score >= min_score:
            filtered_verbs.append(verb)
    
    filtered_verbs = sorted(filtered_verbs)
    
    # Create matrix
    similarity_matrix = np.zeros((len(operation_list), len(filtered_verbs)))
    
    for j, verb in enumerate(filtered_verbs):
        for i, op in enumerate(operation_list):
            if op in scores[verb]:
                score = scores[verb][op]
                # Map "set" to "write" and "get" to "read"
                if op == "get":
                    op = "read"
                if op == "set":
                    op = "write"
                similarity_matrix[i, j] = score
    
    # Create heatmap
    fig_width = max(12, len(filtered_verbs) * 0.5)
    plt.figure(figsize=(fig_width, 5))
    
    operation_list = ["write", "read", "insert", "remove"]
    sns.heatmap(
        similarity_matrix,
        xticklabels=filtered_verbs,
        yticklabels=operation_list,
        annot=False,
        fmt='.2f',
        cmap='RdYlGn',
        center=0.2,
        vmin=-0.1,
        vmax=0.5,
        linewidths=0.5,
        annot_kws={"size": 8}
    )
    
    plt.xlabel('Verbs in API descriptions', fontsize=14)
    plt.ylabel('Memory Operations', fontsize=14)
    plt.xticks(rotation=45, ha='right', fontsize=13)
    plt.yticks(rotation=0, fontsize=13)
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.show()
    
    print(f"Filtered heatmap saved to: {output_file}")
    print(f"Showing {len(filtered_verbs)} verbs with max score >= {min_score}")
    
    return similarity_matrix, filtered_verbs


def create_top_verbs_heatmap(filepath, top_n=30, output_file='verb_heatmap_top.png'):
    """
    Create heatmap with only top N verbs (by max score).
    - X-axis: Top verbs
    - Y-axis: Operations
    """
    scores = read_verb_scores(filepath)
    operation_list = ["set", "get", "insert", "remove"]
    
    # Get top first N verbs by alphabetical orders
    verb_max_scores = [(verb, max(op_scores.values())) for verb, op_scores in scores.items()]
    verb_max_scores.sort(key=lambda x: x[0])  # Sort by verb name

    # Take top N
    top_verbs = [v[0] for v in verb_max_scores[:top_n]]
    
    # Create matrix
    similarity_matrix = np.zeros((len(operation_list), len(top_verbs)))
    
    for j, verb in enumerate(top_verbs):
        for i, op in enumerate(operation_list):
            if op in scores[verb]:
                similarity_matrix[i, j] = scores[verb][op]
    
    # Create heatmap
    fig_width = max(12, len(top_verbs) * 0.6)
    plt.figure(figsize=(fig_width, 5))
    
    # I dont want to add the score value in each cell, what should I do?
    annot = False
    sns.heatmap(
        similarity_matrix,
        xticklabels=top_verbs,
        yticklabels=operation_list,
        annot=annot,
        fmt='.2f',
        cmap='RdYlGn',
        center=0.2,
        vmin=-0.1,
        vmax=0.5,
        linewidths=0.5,
        annot_kws={"size": 9}
    )
    
    #plt.title(f'Top {top_n} Verbs by Cosine Similarity Score', fontsize=14)
    plt.xlabel('Verbs in API descriptions', fontsize=12)
    plt.ylabel('Verbs used for Memory Operations', fontsize=12)
    plt.xticks(rotation=45, ha='right', fontsize=9)
    plt.yticks(rotation=0, fontsize=10)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.show()
    
    print(f"Top {top_n} verbs heatmap saved to: {output_file}")


# Main execution
if __name__ == "__main__":
    filepath = "../data/output/verbs_mpnet.txt"
    
    # Option 1: Full heatmap (all verbs)
    #print("Creating full heatmap (swapped axes)...")
    #create_heatmap_swapped(filepath, output_file='verb_heatmap_full_swapped.png')
    
    # Option 2: Filtered heatmap (high scores only)
    #print("\nCreating filtered heatmap...")
    create_filtered_heatmap_swapped(filepath, min_score=0.24, output_file='verb_heatmap_filtered_swapped.png')
    
    # Option 3: Top N verbs only
    print("\nCreating top 30 verbs heatmap...")
    create_top_verbs_heatmap(filepath, top_n=25, output_file='verb_heatmap_top30.png')
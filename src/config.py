prompt_modes = ["manualPrompt", "autoPrompt_FourTypes"]

gpt_modes = ["eager", "lazy"]

# For safety, we hide the OpenAI keys
# If you want to run DAInfer, please specify the keys
global_openai_key = "***REMOVED***"


# The parameters for self-consistency
global_n = 1  # Default value
global_m = 1  # Default value

# The temperature settings of the two-staged prompting
global_t1 = 0.7  # Default value
global_t2 = 0.7  # Default value


tagTokenCnt = 0
LLMTokenCnt = 0
LLMInputTokenCnt = 0
LLMOutputTokenCnt = 0
LLMTime = 0.0

# The parameters for LLM usage statistics
promptMode = "dataflow_few" # dataflow_zero or dataflow_few
discarded_alias_queries = 0
global_num_queries = {}
global_num_tokens = {}
global_num_descriptions_queried = {}
global_api_description_set = []

# Configuration for embedding model 
vector_dim = 384  # Default dimension for sentencebert all-MiniLM-L6-v2
memory_latency = 0.01  # in seconds
vector_shape = (1, vector_dim)
memory_usage_mb = 0.0015  # in MB
time_embedding_model = 0.0  # in seconds
count_embedding_model = 0   # number of times embedding model is called
EMBEDTime = 0.0

EMBEDDING_MODEL = "e5" # , e5, sentencebert
LLM = 'deepseek-v2:16b'
OMTCnt = 0
SMTCnt = 0

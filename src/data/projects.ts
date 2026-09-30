export type Project = {
  title: string;
  description: string;
  link: string;
  tags: string[];
};

const projects: Project[] = [
  {
    title: 'Document Intelligence with Fine-Tuned Vision-Language Model',
    description: 'Fine-tuned Qwen-VL 7B on FUNSD and DocVQA using supervised fine-tuning and structured prompts for key-value extraction from noisy forms. Optimized with LoRA/QLoRA and model quantization on AWS NVIDIA A100, increasing F1 score to 89%.',
    link: '#',
    tags: ['Python', 'Qwen-VL', 'Hugging Face', 'LoRA/QLoRA', 'AWS']
  },
  {
    title: 'Enterprise RAG Pipeline for Financial Records',
    description: 'Delivered a RAG application using GPT-4 through the OpenAI API, LangChain, FAISS, and Pinecone. Combined vector embeddings and semantic retrieval across millions of financial records to improve retrieval accuracy by approximately 35%.',
    link: '#',
    tags: ['OpenAI GPT-4', 'LangChain', 'FAISS', 'Pinecone', 'Python']
  },
  {
    title: 'Real-time Transaction Fraud Detection Network',
    description: 'Designed a PyTorch deep neural network and tree-based models for real-time transaction fraud detection, applying SMOTE to imbalanced datasets. Productionized as FastAPI services on AWS SageMaker Endpoints for sub-200 ms inference.',
    link: '#',
    tags: ['PyTorch', 'FastAPI', 'AWS SageMaker', 'SMOTE']
  },
  {
    title: 'Financial Sentiment Analysis (FinBERT)',
    description: 'Fine-tuned FinBERT and transformer-based NLP models with Hugging Face for financial sentiment analysis and named entity recognition, achieving a 91% F1 score on production workloads.',
    link: '#',
    tags: ['FinBERT', 'NLP', 'Hugging Face', 'Transformers']
  }
];

export default projects;



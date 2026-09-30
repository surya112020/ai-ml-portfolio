export type Project = {
  title: string;
  description: string;
  link: string;
  tags: string[];
};

const projects: Project[] = [
  {
    title: 'Advanced GraphRAG System',
    description: 'A graph-based Retrieval-Augmented Generation pipeline using Neo4j and LlamaIndex. Builds and queries semantic knowledge graphs from unstructured text corpus, improving multi-hop Q&A accuracy by 45%.',
    link: 'https://github.com/surya112020/cognitive-graphrag',
    tags: ['GraphRAG', 'LlamaIndex', 'Neo4j', 'Knowledge Graphs', 'Python']
  },
  {
    title: 'JobFlow AI (LinkedIn Job Search Agent)',
    description: 'A recruitment intelligence dashboard that automates LinkedIn job scraping using Apify and evaluates job description relevance, tailors resumes, and generates personalized outreach emails.',
    link: 'https://github.com/surya112020/jobflow-ai',
    tags: ['Flask', 'Express', 'Apify Scraper', 'Resume Tailoring', 'OpenAI']
  },
  {
    title: 'GGCPA AI Tax Platform',
    description: 'AI-driven tax platform built to automate tax document parsing and intelligence workflows. Incorporates modern NLP techniques to streamline CPA duties.',
    link: 'https://github.com/surya112020/ggcpa-ai-tax-platform',
    tags: ['AI', 'NLP', 'Automation', 'Python']
  },
  {
    title: 'Document Intelligence with Fine-Tuned Vision-Language Model',
    description: 'Fine-tuned Qwen-VL 7B on FUNSD and DocVQA using supervised fine-tuning and structured prompts for key-value extraction from noisy forms. Optimized with LoRA/QLoRA and model quantization on AWS NVIDIA A100, increasing F1 score to 89%.',
    link: 'https://github.com/surya112020/ai-ml-portfolio',
    tags: ['Python', 'Qwen-VL', 'Hugging Face', 'LoRA/QLoRA', 'AWS']
  },
  {
    title: 'Enterprise RAG Pipeline for Financial Records',
    description: 'Delivered a RAG application using GPT-4 through the OpenAI API, LangChain, FAISS, and Pinecone. Combined vector embeddings and semantic retrieval across millions of financial records to improve retrieval accuracy by approximately 35%.',
    link: 'https://github.com/surya112020/ai-ml-portfolio',
    tags: ['OpenAI GPT-4', 'LangChain', 'FAISS', 'Pinecone', 'Python']
  },
  {
    title: 'Real-time Transaction Fraud Detection Network',
    description: 'Designed a PyTorch deep neural network and tree-based models for real-time transaction fraud detection, applying SMOTE to imbalanced datasets. Productionized as FastAPI services on AWS SageMaker Endpoints for sub-200 ms inference.',
    link: 'https://github.com/surya112020/ai-ml-portfolio',
    tags: ['PyTorch', 'FastAPI', 'AWS SageMaker', 'SMOTE']
  }
];

export default projects;



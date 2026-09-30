import ProjectCard from './components/ProjectCard';
import projects from './data/projects';

function App() {
  return (
    <div className="app-shell">
      <header className="hero-section">
        <div>
          <p className="eyebrow">AI/ML Engineer & Generative AI Specialist</p>
          <h1>Hi, I’m Surya Teja.</h1>
          <p className="hero-copy">
            I design and deploy production-grade Machine Learning, Deep Learning, NLP, 
            and Generative AI systems for financial services and enterprise data environments.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href="#experience">Experience</a>
            <a className="button button-secondary" href="#projects">Projects</a>
            <a className="button button-secondary" href="#contact">Contact</a>
          </div>
        </div>
      </header>

      <section id="about" className="section-card">
        <div>
          <h2>About Me</h2>
          <p>
            I’m an AI/ML Engineer with 4.5 years of experience building end-to-end machine learning, deep learning, NLP, 
            and Generative AI solutions. My domain expertise spans financial services, fraud detection, risk analytics, 
            and enterprise data environments.
          </p>
          <p>
            I specialize in Retrieval-Augmented Generation (RAG), Semantic Search, and Document Intelligence. 
            My technical stack includes Python, PyTorch, Hugging Face Transformers, LLM Fine-Tuning (LoRA/QLoRA), 
            and deploying real-time low-latency inference endpoints on AWS.
          </p>
        </div>
      </section>

      <section id="experience" className="section-card">
        <div>
          <div className="section-title-row">
            <h2>Experience</h2>
          </div>
          <div className="experience-list">
            <div className="experience-item">
              <div className="experience-header">
                <h3>AI/ML Engineer</h3>
                <span className="experience-date">Aug 2025 – Present</span>
              </div>
              <p className="experience-company">IBM, TX, USA</p>
              <ul>
                <li>Engineered scalable PySpark and SQL pipelines on AWS to ingest and process 2 TB+ of financial data daily.</li>
                <li>Built real-time data processing layer with Apache Kafka and Spark Structured Streaming.</li>
                <li>Delivered a RAG application using GPT-4, LangChain, FAISS, and Pinecone, cutting response time to under 3 seconds.</li>
                <li>Fine-tuned FinBERT for financial sentiment analysis and designed comprehensive LLM evaluation controls.</li>
              </ul>
            </div>
            
            <div className="experience-item">
              <div className="experience-header">
                <h3>AI/ML Engineer</h3>
                <span className="experience-date">Jan 2023 – Aug 2024</span>
              </div>
              <p className="experience-company">Capgemini, India</p>
              <ul>
                <li>Designed a PyTorch deep neural network for real-time transaction fraud detection, reducing false positives by 31%.</li>
                <li>Developed BERT-based NLP pipelines using Hugging Face Transformers to extract entities and sentiment from KYC documents.</li>
                <li>Productionized models as FastAPI services on AWS SageMaker Endpoints for sub-200 ms inference.</li>
              </ul>
            </div>

            <div className="experience-item">
              <div className="experience-header">
                <h3>Machine Learning Engineer</h3>
                <span className="experience-date">Jun 2021 – Dec 2022</span>
              </div>
              <p className="experience-company">Deloitte, India</p>
              <ul>
                <li>Developed supervised fraud-classification models with XGBoost and LightGBM for 5M+ daily banking transactions.</li>
                <li>Created multi-terabyte data-preparation pipelines with Python, Spark, and SQL.</li>
                <li>Productionized fraud scoring through Flask REST APIs, Kafka, and SageMaker Endpoints.</li>
                <li>Automated retraining and model versioning with Apache Airflow and MLflow workflows.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section id="projects" className="section-card">
        <div>
          <div className="section-title-row">
            <h2>Projects</h2>
            <p>
              Selected AI/ML and GenAI systems demonstrating fine-tuning, retrieval optimization, 
              and low-latency serving.
            </p>
          </div>
          <div className="project-grid">
            {projects.map((project) => (
              <ProjectCard key={project.title} project={project} />
            ))}
          </div>
        </div>
      </section>

      <section id="contact" className="section-card contact-card">
        <div>
          <h2>Contact</h2>
          <p>
            Want to collaborate on building next-generation cognitive systems or learn more 
            about my work? Send me an email at <strong>suryateja6842@gmail.com</strong> or visit my LinkedIn/GitHub.
          </p>
          <div className="contact-actions">
            <a className="button button-primary" href="mailto:suryateja6842@gmail.com">
              Email Me
            </a>
            <a className="button button-secondary" href="https://github.com/surya112020" target="_blank" rel="noreferrer">
              GitHub
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}

export default App;


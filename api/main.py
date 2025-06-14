from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import base64
import json
import os

from src.scraper import load_discourse_posts, scrape_course_content # scrape_course_content is now a placeholder

# For RAG
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI

app = FastAPI()

# Initialize OpenAI client
# It will automatically pick up OPENAI_API_KEY from environment variables
client = OpenAI(api_key="eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjI0ZjEwMDE5MjlAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.hAdd66pEuxVok50AylYiIoS5XWqdGFDNQC0fAEwMtLI")

# Load Sentence Transformer model globally
# Choosing a good model is crucial. 'all-MiniLM-L6-v2' is a good balance of size and performance.
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# Global variables for loaded data and their embeddings
course_content_data = []
course_content_embeddings = []
discourse_posts_data = []
discourse_posts_embeddings = []

@app.on_event("startup")
async def load_data_and_embeddings():
    global course_content_data, course_content_embeddings
    global discourse_posts_data, discourse_posts_embeddings
    
    print("Application startup: Loading data and generating embeddings...")

    # 1. Load Course Content Data
    # Simulate loading from data/course_content.json (assumes manual population)
    try:
        with open("data/course_content.json", 'r', encoding='utf-8') as f:
            course_content_data = json.load(f)
        print(f"Loaded {len(course_content_data)} course content entries.")
    except FileNotFoundError:
        print("data/course_content.json not found. Course content will be empty.")
    except json.JSONDecodeError:
        print("Error decoding data/course_content.json. Course content will be empty.")

    # 2. Load Discourse Posts Data
    discourse_posts_data = load_discourse_posts() # This function now reads from data/discourse_posts.json

    # 3. Generate Embeddings for Course Content
    if course_content_data:
        print("Generating embeddings for course content...")
        course_texts = [entry["content"] for entry in course_content_data if "content" in entry]
        if course_texts:
            course_content_embeddings = embedding_model.encode(course_texts, show_progress_bar=False)
            print(f"Generated {len(course_content_embeddings)} embeddings for course content.")
        else:
            print("No content found in course_content.json to embed.")

    # 4. Generate Embeddings for Discourse Posts
    if discourse_posts_data:
        print("Generating embeddings for discourse posts...")
        discourse_texts = [entry["content"] for entry in discourse_posts_data if "content" in entry]
        if discourse_texts:
            discourse_posts_embeddings = embedding_model.encode(discourse_texts, show_progress_bar=False)
            print(f"Generated {len(discourse_posts_embeddings)} embeddings for discourse posts.")
        else:
            print("No content found in discourse_posts.json to embed.")

    print("Application startup complete.")

class QuestionRequest(BaseModel):
    question: str
    image: Optional[str] = None

class Link(BaseModel):
    url: str
    text: str

class AnswerResponse(BaseModel):
    answer: str
    links: List[Link]

@app.post("/api/", response_model=AnswerResponse)
async def answer_question(request: QuestionRequest):
    """
    API endpoint to answer student questions using RAG.
    """
    # TODO: Process image data if provided (e.g., OCR, multimodal LLM)
    if request.image:
        try:
            image_data = base64.b64decode(request.image)
            print("Received image data (decoded). Size:", len(image_data), "bytes")
            # Implement image processing here, e.g., using an OCR library or passing to a multimodal model
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")

    student_question_embedding = embedding_model.encode([request.question], show_progress_bar=False)[0]

    relevant_docs = []
    retrieved_links = set() # Use a set to store unique URLs
    
    # Retrieve from Course Content
    if course_content_embeddings.any(): # Check if embeddings are not empty
        similarities = cosine_similarity([student_question_embedding], course_content_embeddings)[0]
        top_indices = similarities.argsort()[-2:][::-1] # Get top 2 most similar
        for i in top_indices:
            if similarities[i] > 0.5: # Threshold for relevance
                doc = course_content_data[i]
                relevant_docs.append(doc["content"])
                # Course content doesn't have URLs in the provided structure, add a placeholder if desired
                # For now, not adding links from course_content unless explicit URLs are added to its data structure

    # Retrieve from Discourse Posts
    if discourse_posts_embeddings.any(): # Check if embeddings are not empty
        similarities = cosine_similarity([student_question_embedding], discourse_posts_embeddings)[0]
        top_indices = similarities.argsort()[-3:][::-1] # Get top 3 most similar
        for i in top_indices:
            if similarities[i] > 0.5: # Threshold for relevance
                doc = discourse_posts_data[i]
                relevant_docs.append(doc["content"])
                if "url" in doc and "title" in doc: # Assuming 'title' can be used as link text
                    retrieved_links.add((doc["url"], doc["title"]))

    context = "\n\n".join(relevant_docs)

    # Fallback if no relevant documents are found
    if not context:
        context = "No highly relevant information found in the knowledge base." # Default context
    
    # Construct prompt for LLM
    prompt = f"""
    You are a clever student who has joined IIT Madras' Online Degree in Data Science. 
    You are acting as a Virtual Teaching Assistant for the Tools in Data Science course. 
    Answer the following student question based ONLY on the provided context. 
    If the question cannot be answered from the context, state that you don't have enough information. 
    Be concise and helpful.

    Student Question: {request.question}

    Context: 
    {context}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful teaching assistant for a Data Science course."
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-3.5-turbo-0125", # As specified in the problem description
            temperature=0.7 # Adjust as needed for creativity vs. factualness
        )
        answer_text = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        answer_text = "I am sorry, but I am currently unable to generate an answer. There was an issue with the AI service." 
        # Add a placeholder link if API call fails
        retrieved_links.add(("https://example.com/error-info", "Error details"))

    # Prepare links for the response
    response_links = []
    for url, text in retrieved_links:
        response_links.append({"url": url, "text": text})

    # If no specific links were retrieved, add a generic placeholder link as per original requirements
    if not response_links and not request.image: # Don't add if image was provided and handled differently
        response_links.append({"url": "https://example.com/general-info", "text": "General course information"})

    return AnswerResponse(answer=answer_text, links=response_links)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
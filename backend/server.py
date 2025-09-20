from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import base64
import io
from PIL import Image
from emergentintegrations.llm.chat import LlmChat, UserMessage
import json

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Initialize LLM Chat
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

# Define Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    user_type: str  # "artisan" or "buyer"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    user_type: str

class UserLogin(BaseModel):
    email: str
    password: str

class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    artisan_id: str
    title: str
    description: str
    price: float
    category: str
    images: List[str] = []
    story: Optional[str] = None
    cultural_context: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProductCreate(BaseModel):
    title: str
    description: str
    price: float
    category: str
    images: List[str] = []

class AIProductRequest(BaseModel):
    image_data: str  # base64 encoded image
    simple_description: Optional[str] = None

class AIStoryRequest(BaseModel):
    product_id: Optional[str] = None
    simple_text: str
    artisan_name: str
    craft_type: str
    cultural_background: Optional[str] = None

class AISocialMediaRequest(BaseModel):
    product_id: str
    platform: str  # "instagram", "facebook", "twitter"

class Story(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    artisan_id: str
    title: str
    content: str
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StoryCreate(BaseModel):
    title: str
    content: str
    audio_url: Optional[str] = None
    video_url: Optional[str] = None

class SocialMediaContent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    artisan_id: str
    product_id: str
    platform: str
    content: str
    hashtags: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Helper Functions
async def get_llm_chat():
    return LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"artisan_assistant_{uuid.uuid4()}",
        system_message="You are an AI assistant specialized in helping local artisans market their traditional crafts and tell their cultural stories."
    ).with_model("openai", "gpt-4o")

def prepare_for_mongo(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
    return data

def parse_from_mongo(item):
    if isinstance(item, dict):
        for key, value in item.items():
            if key.endswith('_at') and isinstance(value, str):
                try:
                    item[key] = datetime.fromisoformat(value)
                except:
                    pass
    return item

# Authentication Routes
@api_router.post("/auth/register", response_model=User)
async def register_user(user_data: UserCreate):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(**user_data.dict(exclude={"password"}))
    user_dict = prepare_for_mongo(user.dict())
    await db.users.insert_one(user_dict)
    return user

@api_router.post("/auth/login")
async def login_user(login_data: UserLogin):
    user = await db.users.find_one({"email": login_data.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # In production, you'd verify the password hash here
    user = parse_from_mongo(user)
    return {"user": User(**user), "token": f"token_{user['id']}"}

# AI-Powered Product Cataloging with Image Upload
@api_router.post("/ai/analyze-product-image")
async def analyze_uploaded_product_image(
    image: UploadFile = File(...),
    description: Optional[str] = Form(None)
):
    try:
        # Validate image file
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read and encode image
        image_bytes = await image.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Get AI chat instance
        chat = await get_llm_chat()
        
        # Create comprehensive prompt for product analysis
        prompt = f"""
        You are an expert in traditional Indian crafts and marketplace analysis. Analyze this product image of a handcrafted item and provide detailed suggestions for an artisan marketplace.

        Additional context from artisan: {description or "Traditional handcrafted item"}
        
        Provide a comprehensive analysis in JSON format:
        {{
            "title": "compelling product title (max 60 characters)",
            "description": "detailed 2-3 paragraph description highlighting craftsmanship, materials, and cultural significance",
            "suggested_price": "single price in INR (number only)",
            "price_range": "price range like '1500-2500 INR'",
            "category": "product category (e.g., Textiles, Jewelry, Home Decor, etc.)",
            "materials": ["list of materials used"],
            "techniques": ["traditional techniques involved"],
            "cultural_context": "cultural and regional significance",
            "target_audience": "who would be interested in this product",
            "care_instructions": "how to maintain the product",
            "key_features": ["unique selling points"],
            "occasions": ["suitable occasions for use/gifting"],
            "color_palette": ["dominant colors in the product"],
            "estimated_time_to_make": "time needed to craft this item"
        }}
        
        Make the content authentic, culturally respectful, and market-ready.
        """
        
        message = UserMessage(text=prompt)
        response = await chat.send_message(message)
        
        # Try to parse the JSON response
        try:
            # Clean the response if it has markdown formatting
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            ai_data = json.loads(clean_response)
            
            return {
                "ai_analysis": ai_data,
                "image_url": f"data:image/jpeg;base64,{image_base64[:100]}...",  # Preview
                "status": "success"
            }
        except json.JSONDecodeError:
            # If JSON parsing fails, return the raw response
            return {
                "ai_analysis": {"raw_response": response},
                "image_url": f"data:image/jpeg;base64,{image_base64[:100]}...",
                "status": "success"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")

# Keep the old endpoint for backward compatibility
@api_router.post("/ai/analyze-product")
async def analyze_product_image(request: AIProductRequest):
    try:
        chat = await get_llm_chat()
        
        # Create prompt for product analysis
        prompt = f"""
        Analyze this product and generate:
        1. A compelling product title (max 60 characters)
        2. A detailed product description (2-3 paragraphs)
        3. Suggested price range in INR
        4. Product category
        5. Key features and selling points
        
        Additional context: {request.simple_description or "Traditional handcrafted item"}
        
        Format your response as JSON:
        {{
            "title": "suggested title",
            "description": "detailed description",
            "price_range": "1000-2000 INR",
            "category": "category name",
            "features": ["feature 1", "feature 2"],
            "cultural_significance": "brief cultural context"
        }}
        """
        
        message = UserMessage(text=prompt)
        response = await chat.send_message(message)
        
        return {"ai_suggestions": response, "status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")

# AI Storytelling Assistant with Image Context
@api_router.post("/ai/generate-story-with-image")
async def generate_story_with_image(
    image: Optional[UploadFile] = File(None),
    artisan_name: str = Form(...),
    craft_type: str = Form(...),
    simple_text: str = Form(...),
    cultural_background: Optional[str] = Form(None)
):
    try:
        chat = await get_llm_chat()
        
        image_context = ""
        image_base64 = None
        
        # Process image if provided
        if image:
            if not image.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="File must be an image")
            
            image_bytes = await image.read()
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            image_context = " Based on the image provided showing the craft/artisan at work,"
        
        prompt = f"""
        You are a storytelling expert specializing in preserving and sharing cultural heritage stories. Create an engaging artisan story based on this information:
        
        Artisan Name: {artisan_name}
        Craft Type: {craft_type}
        Artisan's Description: {simple_text}
        Cultural Background: {cultural_background or "Traditional Indian craftsmanship"}
        {image_context}
        
        Create a compelling story that includes:
        1. A captivating title that reflects the artisan's journey
        2. A rich 4-5 paragraph narrative covering:
           - The artisan's personal background and how they learned the craft
           - Detailed description of traditional techniques and materials
           - Cultural and historical significance of their craft
           - Challenges faced and overcome in preserving tradition
           - Vision for passing on the craft to future generations
        3. Cultural highlights and traditional techniques
        
        Make it authentic, emotionally engaging, and respectful of cultural heritage.
        
        Format as JSON:
        {{
            "title": "compelling story title",
            "story": "full narrative story (4-5 paragraphs)",
            "short_summary": "2-sentence summary for previews",
            "cultural_highlights": ["cultural aspect 1", "cultural aspect 2", "cultural aspect 3"],
            "traditional_techniques": ["technique 1", "technique 2", "technique 3"],
            "heritage_significance": "why this craft is important for cultural preservation",
            "artisan_quote": "a meaningful quote that could be attributed to the artisan",
            "story_tags": ["tag1", "tag2", "tag3"],
            "estimated_read_time": "X minutes"
        }}
        """
        
        message = UserMessage(text=prompt)
        response = await chat.send_message(message)
        
        # Try to parse JSON response
        try:
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            story_data = json.loads(clean_response)
            
            result = {
                "story_content": story_data,
                "status": "success"
            }
            
            if image_base64:
                result["image_preview"] = f"data:image/jpeg;base64,{image_base64[:100]}..."
            
            return result
            
        except json.JSONDecodeError:
            return {
                "story_content": {"raw_response": response},
                "status": "success",
                "image_preview": f"data:image/jpeg;base64,{image_base64[:100]}..." if image_base64 else None
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Story generation failed: {str(e)}")

# Keep the old endpoint for backward compatibility
@api_router.post("/ai/generate-story")
async def generate_artisan_story(request: AIStoryRequest):
    try:
        chat = await get_llm_chat()
        
        prompt = f"""
        Create an engaging artisan story based on this information:
        
        Artisan: {request.artisan_name}
        Craft Type: {request.craft_type}
        Simple Description: {request.simple_text}
        Cultural Background: {request.cultural_background or "Traditional Indian craftsmanship"}
        
        Generate:
        1. A compelling story title
        2. An engaging 3-4 paragraph story that includes:
           - The artisan's heritage and background
           - The traditional techniques used
           - Cultural significance of the craft
           - Personal touch and passion
           - Connection to community and tradition
        
        Make it authentic, respectful, and emotionally engaging.
        
        Format as JSON:
        {{
            "title": "story title",
            "story": "full story content",
            "cultural_highlights": ["highlight 1", "highlight 2"],
            "traditional_techniques": ["technique 1", "technique 2"]
        }}
        """
        
        message = UserMessage(text=prompt)
        response = await chat.send_message(message)
        
        return {"story_content": response, "status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Story generation failed: {str(e)}")

# AI Social Media Content Generator
@api_router.post("/ai/generate-social-content")
async def generate_social_media_content(request: AISocialMediaRequest):
    try:
        # Get product details
        product = await db.products.find_one({"id": request.product_id})
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        chat = await get_llm_chat()
        
        platform_specs = {
            "instagram": "Instagram post with engaging caption, emojis, and hashtags. Include call-to-action.",
            "facebook": "Facebook post with storytelling approach, longer description, and community engagement.",
            "twitter": "Twitter thread with multiple tweets, concise but impactful messages."
        }
        
        prompt = f"""
        Create {request.platform} content for this product:
        
        Product: {product.get('title', 'Handcrafted Item')}
        Description: {product.get('description', 'Beautiful traditional craft')}
        Category: {product.get('category', 'Traditional Crafts')}
        
        Platform: {request.platform}
        Requirements: {platform_specs.get(request.platform, "General social media post")}
        
        Generate:
        1. Main post content
        2. Relevant hashtags (10-15 for Instagram, 5-8 for others)
        3. Call-to-action
        4. Story highlights (for Instagram stories)
        
        Focus on cultural heritage, traditional craftsmanship, and supporting local artisans.
        
        Format as JSON:
        {{
            "main_content": "post content",
            "hashtags": ["#tag1", "#tag2"],
            "call_to_action": "CTA text",
            "story_highlights": ["highlight 1", "highlight 2"],
            "best_posting_time": "suggested time"
        }}
        """
        
        message = UserMessage(text=prompt)
        response = await chat.send_message(message)
        
        return {"social_content": response, "platform": request.platform, "status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Social content generation failed: {str(e)}")

# AI Multilingual Translation
@api_router.post("/ai/translate")
async def translate_content():
    try:
        chat = await get_llm_chat()
        
        prompt = """
        Translate this product description to Hindi, Tamil, Bengali, and Gujarati:
        
        "Beautiful handwoven silk saree with traditional motifs. This exquisite piece represents generations of skilled craftsmanship."
        
        Provide translations that maintain cultural authenticity and appeal.
        
        Format as JSON with language codes.
        """
        
        message = UserMessage(text=prompt)
        response = await chat.send_message(message)
        
        return {"translations": response, "status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

# AI Personalized Recommendations
@api_router.get("/ai/recommendations/{user_id}")
async def get_personalized_recommendations(user_id: str):
    try:
        # Get user's browsing history and preferences
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get some sample products for recommendation
        products = await db.products.find().limit(10).to_list(10)
        
        chat = await get_llm_chat()
        
        prompt = f"""
        Generate personalized product recommendations for a user interested in traditional Indian crafts.
        
        User Profile: {user.get('user_type', 'buyer')} interested in cultural products
        
        Available products: {len(products)} traditional craft items
        
        Recommend 5 products with reasons based on:
        1. Cultural interest
        2. Seasonal relevance
        3. Gifting occasions
        4. Price range preferences
        
        Format as JSON:
        {{
            "recommendations": [
                {{
                    "reason": "why recommended",
                    "occasion": "suitable for",
                    "cultural_appeal": "cultural significance"
                }}
            ]
        }}
        """
        
        message = UserMessage(text=prompt)
        response = await chat.send_message(message)
        
        return {"recommendations": response, "user_id": user_id, "status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")

# Product Routes
@api_router.post("/products", response_model=Product)
async def create_product(product_data: ProductCreate, artisan_id: str = Form(...)):
    product = Product(**product_data.dict(), artisan_id=artisan_id)
    product_dict = prepare_for_mongo(product.dict())
    await db.products.insert_one(product_dict)
    return product

@api_router.get("/products", response_model=List[Product])
async def get_products():
    products = await db.products.find().to_list(100)
    return [Product(**parse_from_mongo(product)) for product in products]

@api_router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return Product(**parse_from_mongo(product))

# Artisan Stories Routes
@api_router.post("/stories", response_model=Story)
async def create_story(story_data: StoryCreate, artisan_id: str = Form(...)):
    story = Story(**story_data.dict(), artisan_id=artisan_id)
    story_dict = prepare_for_mongo(story.dict())
    await db.stories.insert_one(story_dict)
    return story

@api_router.get("/stories", response_model=List[Story])
async def get_stories():
    stories = await db.stories.find().to_list(50)
    return [Story(**parse_from_mongo(story)) for story in stories]

@api_router.get("/stories/artisan/{artisan_id}", response_model=List[Story])
async def get_artisan_stories(artisan_id: str):
    stories = await db.stories.find({"artisan_id": artisan_id}).to_list(50)
    return [Story(**parse_from_mongo(story)) for story in stories]

# Test route
@api_router.get("/")
async def root():
    return {"message": "AI-Powered Marketplace Assistant API", "status": "active"}

@api_router.get("/test-ai")
async def test_ai():
    try:
        chat = await get_llm_chat()
        message = UserMessage(text="Say 'AI integration successful for Artisan Marketplace!' and nothing else.")
        response = await chat.send_message(message)
        return {"ai_response": response, "status": "success"}
    except Exception as e:
        return {"error": str(e), "status": "failed"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
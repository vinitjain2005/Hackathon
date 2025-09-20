import requests
import sys
import json
from datetime import datetime

class ArtisanMarketplaceAPITester:
    def __init__(self, base_url="https://artisanreach-1.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        
        result = f"{status} - {name}"
        if details:
            result += f" | {details}"
        
        print(result)
        self.test_results.append({
            'name': name,
            'success': success,
            'details': details
        })
        return success

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}" if not endpoint.startswith('http') else endpoint
        test_headers = {'Content-Type': 'application/json'}
        
        if headers:
            test_headers.update(headers)
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            details = f"Status: {response.status_code}"
            
            if success:
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict) and len(str(response_data)) < 200:
                        details += f" | Response: {response_data}"
                except:
                    details += f" | Response: {response.text[:100]}"
            else:
                details += f" | Expected: {expected_status}"
                try:
                    error_data = response.json()
                    details += f" | Error: {error_data}"
                except:
                    details += f" | Error: {response.text[:100]}"

            self.log_test(name, success, details)
            return success, response.json() if success and response.text else {}

        except Exception as e:
            self.log_test(name, False, f"Exception: {str(e)}")
            return False, {}

    def test_basic_connectivity(self):
        """Test basic API connectivity"""
        print("\n🔍 Testing Basic Connectivity...")
        return self.run_test("API Root", "GET", "", 200)

    def test_ai_connection(self):
        """Test AI integration"""
        print("\n🤖 Testing AI Integration...")
        success, response = self.run_test("AI Test", "GET", "test-ai", 200)
        if success and 'ai_response' in response:
            print(f"   AI Response: {response.get('ai_response', 'No response')}")
        return success

    def test_authentication(self):
        """Test user registration and login"""
        print("\n🔐 Testing Authentication...")
        
        # Test user registration
        test_user_data = {
            "email": f"test_artisan_{datetime.now().strftime('%H%M%S')}@example.com",
            "name": "Test Artisan",
            "password": "TestPass123!",
            "user_type": "artisan"
        }
        
        success, response = self.run_test(
            "User Registration", 
            "POST", 
            "auth/register", 
            200, 
            test_user_data
        )
        
        if success and 'id' in response:
            self.user_id = response['id']
            print(f"   Registered user ID: {self.user_id}")
        
        # Test user login
        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        }
        
        login_success, login_response = self.run_test(
            "User Login",
            "POST",
            "auth/login",
            200,
            login_data
        )
        
        if login_success and 'token' in login_response:
            self.token = login_response['token']
            print(f"   Login token: {self.token[:20]}...")
        
        return success and login_success

    def test_ai_features(self):
        """Test AI-powered features"""
        print("\n🎨 Testing AI Features...")
        
        # Test AI Product Analysis
        product_analysis_data = {
            "image_data": "sample_base64_image_data",
            "simple_description": "Beautiful handwoven silk scarf with traditional patterns"
        }
        
        ai_product_success, _ = self.run_test(
            "AI Product Analysis",
            "POST",
            "ai/analyze-product",
            200,
            product_analysis_data
        )
        
        # Test AI Story Generation
        story_data = {
            "artisan_name": "Test Artisan",
            "craft_type": "Traditional Textile Weaving",
            "simple_text": "I have been weaving silk for 20 years, learned from my grandmother",
            "cultural_background": "Rajasthani traditional craftsmanship"
        }
        
        ai_story_success, _ = self.run_test(
            "AI Story Generation",
            "POST",
            "ai/generate-story",
            200,
            story_data
        )
        
        # Test AI Translation
        ai_translate_success, _ = self.run_test(
            "AI Translation",
            "POST",
            "ai/translate",
            200
        )
        
        return ai_product_success and ai_story_success and ai_translate_success

    def test_product_management(self):
        """Test product CRUD operations"""
        print("\n📦 Testing Product Management...")
        
        if not self.user_id:
            self.log_test("Product Management", False, "No user ID available")
            return False
        
        # Test creating a product
        product_data = {
            "title": "Test Handwoven Scarf",
            "description": "Beautiful traditional scarf with intricate patterns",
            "price": 2500.0,
            "category": "Textiles",
            "images": ["https://example.com/image1.jpg"]
        }
        
        # Note: The API expects artisan_id as Form data, but we'll test with JSON first
        create_success, create_response = self.run_test(
            "Create Product",
            "POST",
            "products",
            200,
            {**product_data, "artisan_id": self.user_id}
        )
        
        product_id = None
        if create_success and 'id' in create_response:
            product_id = create_response['id']
            print(f"   Created product ID: {product_id}")
        
        # Test getting all products
        get_all_success, _ = self.run_test(
            "Get All Products",
            "GET",
            "products",
            200
        )
        
        # Test getting single product
        if product_id:
            get_single_success, _ = self.run_test(
                "Get Single Product",
                "GET",
                f"products/{product_id}",
                200
            )
        else:
            get_single_success = True  # Skip if no product created
        
        return create_success and get_all_success and get_single_success

    def test_stories_management(self):
        """Test stories CRUD operations"""
        print("\n📖 Testing Stories Management...")
        
        if not self.user_id:
            self.log_test("Stories Management", False, "No user ID available")
            return False
        
        # Test creating a story
        story_data = {
            "title": "My Craft Journey",
            "content": "This is the story of how I learned traditional weaving from my grandmother...",
            "audio_url": None,
            "video_url": None
        }
        
        create_success, create_response = self.run_test(
            "Create Story",
            "POST",
            "stories",
            200,
            {**story_data, "artisan_id": self.user_id}
        )
        
        # Test getting all stories
        get_all_success, _ = self.run_test(
            "Get All Stories",
            "GET",
            "stories",
            200
        )
        
        # Test getting artisan stories
        get_artisan_success, _ = self.run_test(
            "Get Artisan Stories",
            "GET",
            f"stories/artisan/{self.user_id}",
            200
        )
        
        return create_success and get_all_success and get_artisan_success

    def test_ai_advanced_features(self):
        """Test advanced AI features"""
        print("\n🚀 Testing Advanced AI Features...")
        
        if not self.user_id:
            self.log_test("Advanced AI Features", False, "No user ID available")
            return False
        
        # Test AI Recommendations
        recommendations_success, _ = self.run_test(
            "AI Recommendations",
            "GET",
            f"ai/recommendations/{self.user_id}",
            200
        )
        
        return recommendations_success

    def run_all_tests(self):
        """Run all tests"""
        print("🧪 Starting Artisan Marketplace API Tests...")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Run tests in order
        basic_ok = self.test_basic_connectivity()
        ai_ok = self.test_ai_connection()
        auth_ok = self.test_authentication()
        ai_features_ok = self.test_ai_features()
        products_ok = self.test_product_management()
        stories_ok = self.test_stories_management()
        advanced_ai_ok = self.test_ai_advanced_features()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        # Print failed tests
        failed_tests = [t for t in self.test_results if not t['success']]
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"   • {test['name']}: {test['details']}")
        
        print("\n" + "=" * 60)
        
        return self.tests_passed == self.tests_run

def main():
    tester = ArtisanMarketplaceAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
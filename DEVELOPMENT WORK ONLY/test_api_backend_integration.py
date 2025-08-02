"""
Integration tests for the backend API separation architecture.
Tests all API endpoints and backend router functionality.
"""

import pytest
import json
import os
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from api_backend import api_v1
from backend_router import BackendRouter, BackendInstance, BackendStatus
import requests

class TestAPIBackendIntegration:
    """Test suite for API backend integration"""
    
    @pytest.fixture
    def app(self):
        """Create test Flask app with API blueprint"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
        app.config['PROCESSED_FOLDER'] = tempfile.mkdtemp()
        app.config['PROCESSED_VIDEOS_FOLDER'] = tempfile.mkdtemp()
        
        # Mock resource monitor and queue manager
        app.resource_monitor = Mock()
        app.queue_manager = Mock()
        
        # Register API blueprint
        app.register_blueprint(api_v1)
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    @pytest.fixture
    def auth_headers(self):
        """Mock authentication headers"""
        return {
            'x-access-token': 'test-token-123',
            'Content-Type': 'application/json'
        }
    
    def test_health_check_endpoint(self, client):
        """Test the health check endpoint"""
        response = client.get('/api/v1/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['status'] in ['healthy', 'degraded', 'unhealthy']
        assert 'timestamp' in data
        assert 'version' in data
        assert 'service' in data
        assert data['service'] == 'aiart-backend'
    
    def test_health_check_with_resource_monitor(self, client, app):
        """Test health check with resource monitor data"""
        # Mock resource monitor
        mock_status = {
            'cpu_usage': 45.2,
            'memory_usage': 67.8,
            'load_percentage': 55.0,
            'is_hibernating': False
        }
        
        with patch('api_backend.get_system_status', return_value=mock_status):
            response = client.get('/api/v1/health')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert data['cpu_usage'] == 45.2
            assert data['memory_usage'] == 67.8
            assert data['load_percentage'] == 55.0
            assert data['is_hibernating'] is False
    
    def test_health_check_degraded_status(self, client, app):
        """Test health check returns degraded status under high load"""
        mock_status = {
            'cpu_usage': 95.0,  # High CPU usage
            'memory_usage': 85.0,
            'load_percentage': 90.0,
            'is_hibernating': False
        }
        
        with patch('api_backend.get_system_status', return_value=mock_status):
            response = client.get('/api/v1/health')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            
            assert data['status'] == 'degraded'
    
    def test_cors_headers(self, client):
        """Test CORS headers are properly set"""
        response = client.options('/api/v1/health', 
                                headers={'Origin': 'https://aiart-zroo.onrender.com'})
        
        assert 'Access-Control-Allow-Origin' in response.headers
        assert 'Access-Control-Allow-Methods' in response.headers
        assert 'Access-Control-Allow-Headers' in response.headers
    
    def test_text_to_image_endpoint_missing_token(self, client):
        """Test text-to-image endpoint requires authentication"""
        response = client.post('/api/v1/generate/text-to-image',
                             json={'prompt': 'test prompt'})
        
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Authentication required' in data['error']
    
    def test_text_to_image_endpoint_missing_prompt(self, client, auth_headers):
        """Test text-to-image endpoint requires prompt"""
        response = client.post('/api/v1/generate/text-to-image',
                             json={},
                             headers=auth_headers)
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Missing prompt' in data['error']
    
    def test_text_to_image_endpoint_prompt_too_long(self, client, auth_headers):
        """Test text-to-image endpoint rejects overly long prompts"""
        long_prompt = 'a' * 1001  # Exceeds 1000 character limit
        
        response = client.post('/api/v1/generate/text-to-image',
                             json={'prompt': long_prompt},
                             headers=auth_headers)
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Prompt too long' in data['error']
    
    @patch('api_backend.main_image_function')
    @patch('api_backend.translate_to_english')
    def test_text_to_image_success(self, mock_translate, mock_generate, client, auth_headers):
        """Test successful text-to-image generation"""
        mock_translate.return_value = 'translated prompt'
        mock_generate.return_value = {
            'success': True,
            'image_url': '/images/test.png',
            'seed': 12345
        }
        
        response = client.post('/api/v1/generate/text-to-image',
                             json={'prompt': 'test prompt'},
                             headers=auth_headers)
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'image_url' in data
        assert data['seed'] == 12345
    
    def test_image_to_image_endpoint_missing_image(self, client, auth_headers):
        """Test image-to-image endpoint requires image file"""
        response = client.post('/api/v1/generate/image-to-image',
                             data={'prompt': 'test prompt'},
                             headers={'x-access-token': 'test-token-123'})
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Missing image' in data['error']
    
    def test_text_to_video_endpoint_success(self, client, auth_headers):
        """Test text-to-video endpoint returns task ID"""
        with patch('api_backend.QwenApiKey.get_all', return_value=[{'key': 'test'}]):
            with patch('api_backend.VideoTask.create', return_value={'task_id': 'test-task-123'}):
                response = client.post('/api/v1/generate/text-to-video',
                                     json={'prompt': 'test video prompt'},
                                     headers=auth_headers)
                
                assert response.status_code == 202
                data = json.loads(response.data)
                assert data['success'] is True
                assert data['task_id'] == 'test-task-123'
                assert 'status_url' in data
    
    def test_text_to_video_status_endpoint(self, client):
        """Test text-to-video status endpoint"""
        mock_task = {
            'task_id': 'test-task-123',
            'status': 'completed',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:05:00Z',
            'video_url': '/videos/test.mp4'
        }
        
        with patch('api_backend.VideoTask.get_by_task_id', return_value=mock_task):
            response = client.get('/api/v1/generate/text-to-video/status/test-task-123')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['status'] == 'completed'
            assert data['video_url'] == '/videos/test.mp4'
    
    def test_auth_validate_token_endpoint(self, client):
        """Test token validation endpoint"""
        with patch('api_backend.firebase_admin_auth.verify_id_token') as mock_verify:
            mock_verify.return_value = {'uid': 'test-uid-123'}
            
            with patch('api_backend.User.find_by_firebase_uid') as mock_user:
                mock_user.return_value = Mock(email='test@example.com')
                
                response = client.post('/api/v1/auth/validate-token',
                                     json={'token': 'test-firebase-token'})
                
                assert response.status_code == 200
                data = json.loads(response.data)
                assert data['success'] is True
                assert data['valid'] is True
                assert data['uid'] == 'test-uid-123'
    
    def test_enhance_prompt_endpoint(self, client, auth_headers):
        """Test prompt enhancement endpoint"""
        with patch('api_backend.generate_gemini') as mock_gemini:
            mock_gemini.return_value = 'Enhanced detailed prompt with artistic style'
            
            response = client.post('/api/v1/enhance-prompt',
                                 json={'prompt': 'simple prompt'},
                                 headers=auth_headers)
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['original_prompt'] == 'simple prompt'
            assert 'Enhanced detailed prompt' in data['enhanced_prompt']
    
    def test_rate_limiting_response(self, client, auth_headers):
        """Test rate limiting returns proper response format"""
        with patch('api_backend.adaptive_should_allow_request') as mock_rate_limit:
            mock_rate_limit.return_value = (False, {'tier': 'anonymous', 'server_load': 0.8})
            
            with patch('api_backend.get_rate_limit_message') as mock_message:
                mock_message.return_value = {
                    'title': 'Rate Limit Reached',
                    'message': 'Please wait before making another request',
                    'wait_time': 60,
                    'donation_link': '/donate'
                }
                
                response = client.post('/api/v1/generate/text-to-image',
                                     json={'prompt': 'test prompt'},
                                     headers=auth_headers)
                
                assert response.status_code == 429
                data = json.loads(response.data)
                assert data['success'] is False
                assert data['error_type'] == 'rate_limit'
                assert data['wait_time'] == 60


class TestBackendRouter:
    """Test suite for BackendRouter functionality"""
    
    @pytest.fixture
    def backend_configs(self):
        """Sample backend configurations"""
        return [
            {'url': 'https://primary.example.com', 'name': 'primary', 'priority': 1},
            {'url': 'https://fallback.example.com/', 'name': 'fallback', 'priority': 2}
        ]
    
    @pytest.fixture
    def router(self, backend_configs):
        """Create BackendRouter instance"""
        router = BackendRouter(backend_configs, health_check_interval=1)
        yield router
        router.stop_health_monitoring()
    
    def test_backend_router_initialization(self, router):
        """Test BackendRouter initializes correctly"""
        assert len(router.backends) == 2
        assert router.backends[0].name == 'primary'
        assert router.backends[1].name == 'fallback'
        assert router.backends[0].url == 'https://primary.example.com/'
        assert router.backends[1].url == 'https://fallback.example.com/'
    
    def test_backend_health_score_calculation(self):
        """Test backend health score calculation"""
        backend = BackendInstance(
            url='https://test.example.com',
            name='test',
            status=BackendStatus.HEALTHY
        )
        
        # Healthy backend should have high score
        assert backend.health_score == 1.0
        
        # Add some response time penalty
        backend.response_time = 5.0
        assert backend.health_score < 1.0
        
        # Add error count
        backend.error_count = 10
        backend.success_count = 90
        score_with_errors = backend.health_score
        assert score_with_errors < 0.9
    
    @patch('requests.get')
    def test_backend_health_check_success(self, mock_get, router):
        """Test successful backend health check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'healthy'}
        mock_get.return_value = mock_response
        
        backend = router.backends[0]
        status = router.check_backend_health(backend)
        
        assert status == BackendStatus.HEALTHY
        assert backend.success_count > 0
        assert backend.consecutive_failures == 0
    
    @patch('requests.get')
    def test_backend_health_check_failure(self, mock_get, router):
        """Test backend health check failure"""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        backend = router.backends[0]
        status = router.check_backend_health(backend)
        
        assert status == BackendStatus.DOWN
        assert backend.error_count > 0
        assert backend.consecutive_failures > 0
        assert backend.last_error == "Connection Error"
    
    @patch('requests.get')
    def test_backend_health_check_timeout(self, mock_get, router):
        """Test backend health check timeout"""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        backend = router.backends[0]
        status = router.check_backend_health(backend)
        
        assert status == BackendStatus.DOWN
        assert backend.last_error == "Timeout"
        assert backend.response_time == 10.0
    
    def test_get_available_backend(self, router):
        """Test getting available backend"""
        # Set first backend as healthy
        router.backends[0].status = BackendStatus.HEALTHY
        router.backends[1].status = BackendStatus.DOWN
        
        backend = router.get_available_backend()
        
        assert backend is not None
        assert backend.name == 'primary'
    
    def test_get_available_backend_priority(self, router):
        """Test backend selection respects priority"""
        # Both backends healthy, should select higher priority (lower number)
        router.backends[0].status = BackendStatus.HEALTHY
        router.backends[1].status = BackendStatus.HEALTHY
        
        backend = router.get_available_backend()
        
        assert backend.name == 'primary'  # Priority 1 vs 2
    
    def test_get_available_backend_none_available(self, router):
        """Test when no backends are available"""
        router.backends[0].status = BackendStatus.DOWN
        router.backends[1].status = BackendStatus.DOWN
        
        backend = router.get_available_backend()
        
        assert backend is None
    
    def test_mark_backend_down(self, router):
        """Test marking backend as down"""
        router.mark_backend_down('https://primary.example.com', 'Test error')
        
        backend = router.backends[0]
        assert backend.status == BackendStatus.DOWN
        assert backend.last_error == 'Test error'
        assert backend.consecutive_failures > 0
    
    @patch('requests.request')
    def test_make_request_success(self, mock_request, router):
        """Test successful request through router"""
        # Set up healthy backend
        router.backends[0].status = BackendStatus.HEALTHY
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True, 'data': 'test'}
        mock_request.return_value = mock_response
        
        success, data = router.make_request('test/endpoint', method='POST', json={'test': 'data'})
        
        assert success is True
        assert data['success'] is True
        assert data['data'] == 'test'
    
    @patch('requests.request')
    def test_make_request_failover(self, mock_request, router):
        """Test request failover to secondary backend"""
        # Set both backends as healthy
        router.backends[0].status = BackendStatus.HEALTHY
        router.backends[1].status = BackendStatus.HEALTHY
        
        # First request fails, second succeeds
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {'success': True, 'backend': 'fallback'}
        
        mock_request.side_effect = [
            requests.exceptions.ConnectionError("Connection failed"),
            mock_response_success
        ]
        
        success, data = router.make_request('test/endpoint')
        
        assert success is True
        assert data['backend'] == 'fallback'
    
    @patch('requests.request')
    def test_make_request_all_backends_fail(self, mock_request, router):
        """Test when all backends fail"""
        # Set backends as healthy initially
        router.backends[0].status = BackendStatus.HEALTHY
        router.backends[1].status = BackendStatus.HEALTHY
        
        # All requests fail
        mock_request.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        success, data = router.make_request('test/endpoint')
        
        assert success is False
        assert 'All backends unavailable' in data['error']
    
    def test_get_backend_status(self, router):
        """Test getting backend status summary"""
        status = router.get_backend_status()
        
        assert 'backends' in status
        assert len(status['backends']) == 2
        
        backend_info = status['backends'][0]
        assert 'name' in backend_info
        assert 'url' in backend_info
        assert 'status' in backend_info
        assert 'health_score' in backend_info
        assert 'priority' in backend_info


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
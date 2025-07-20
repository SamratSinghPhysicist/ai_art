# User Generation History Feature

## Overview
This feature allows both logged-in and anonymous users to view their previous text-to-video generations without storing the actual video files on the server. Instead, it uses proxy URLs to display videos while hiding the original Qwen service URLs.

## Key Features

### ✅ User-Friendly Experience
- **Both logged-in and anonymous users** can view their previous generations
- **No Qwen branding** - completely hidden from users (including network logs)
- **Video streaming** without storing files on server
- **Responsive grid layout** showing video thumbnails
- **Modal video player** for full-screen viewing
- **Download functionality** for generated videos

### ✅ Privacy & Security
- **Proxy URLs** hide original Qwen service URLs
- **Session-based tracking** for anonymous users
- **User-based tracking** for logged-in users
- **Automatic cleanup** of expired video mappings
- **Access control** - users can only see their own generations

### ✅ Technical Implementation
- **MongoDB storage** for generation history
- **JWT token authentication** for API access
- **Background video processing** with status tracking
- **Automatic URL mapping** with expiration
- **Real-time updates** when new videos are completed

## Database Schema

### UserGenerationHistory Collection
```javascript
{
  _id: ObjectId,
  user_id: String,           // For logged-in users
  session_id: String,        // For anonymous users  
  generation_type: String,   // "text-to-video"
  prompt: String,           // User's text prompt
  result_url: String,       // Original Qwen URL (hidden)
  proxy_url: String,        // Public proxy URL
  task_id: String,          // Video generation task ID
  generation_params: Object, // Additional parameters
  created_at: Date,         // Generation timestamp
  is_active: Boolean        // For soft deletion
}
```

### VideoUrlMapping Collection
```javascript
{
  _id: ObjectId,
  proxy_id: String,         // UUID for proxy URL
  qwen_url: String,         // Original Qwen video URL
  task_id: String,          // Associated task ID
  created_at: Date,         // Creation timestamp
  expires_at: Date,         // Expiration timestamp
  access_count: Number      // Usage tracking
}
```

## API Endpoints

### GET /api/user-generations
Retrieve user's generation history
- **Authentication**: Required (JWT token)
- **Parameters**: 
  - `type`: Generation type (default: "text-to-video")
  - `limit`: Number of items (max 50, default 20)
  - `skip`: Pagination offset (default 0)
- **Response**: List of user's generations with metadata

### GET /api/user-generations/{id}
Get specific generation by ID
- **Authentication**: Required (JWT token)
- **Response**: Single generation details with ownership verification

### GET /video/{proxy_id}
Stream video through proxy
- **Authentication**: None required
- **Response**: Video stream with hidden original URL

## Frontend Features

### Previous Videos Section
- **Grid layout** showing video thumbnails
- **Hover effects** with play button overlay
- **Status indicators** (Completed, Processing, Failed)
- **Pagination** with "Load More" button
- **Empty state** for users with no generations

### Video Modal
- **Full-screen video player** with controls
- **Keyboard shortcuts** (Escape to close)
- **Click outside to close** functionality
- **Auto-play** when opened

### Integration
- **Automatic refresh** when new videos complete
- **Real-time status updates** during generation
- **Seamless user experience** with existing workflow

## Configuration

### Environment Variables
```bash
VIDEO_MAPPING_CLEANUP_INTERVAL_HOURS=6  # Cleanup frequency
VIDEO_MAPPING_EXPIRATION_HOURS=24       # URL expiration time
```

### Database Indexes
- `user_id + created_at` (compound index)
- `session_id` (single index)
- `generation_type` (single index)
- `proxy_id` (unique index)
- `expires_at` (TTL-style cleanup)

## Usage Examples

### For Anonymous Users
1. Visit `/text-to-video` page
2. Generate videos without logging in
3. View previous generations in same browser session
4. Videos persist until session expires

### For Logged-In Users
1. Login to account
2. Generate videos from any device
3. Access generation history from any device
4. Videos persist across sessions

## Security Considerations

### URL Obfuscation
- Original Qwen URLs are never exposed to frontend
- Proxy URLs use UUIDs (non-guessable)
- Network logs show only proxy URLs

### Access Control
- Users can only access their own generations
- Session-based isolation for anonymous users
- JWT token validation for all API calls

### Data Cleanup
- Automatic cleanup of expired URL mappings
- Configurable retention periods
- Soft deletion for generation history

## Testing

Run the test suite:
```bash
python test_user_generations.py
```

This will verify:
- Database model functionality
- API endpoint security
- URL mapping system
- Basic CRUD operations

## Monitoring

### Admin Dashboard
- View video proxy performance metrics
- Monitor URL mapping storage usage
- Track error rates and response times
- Manual cleanup of expired mappings

### Health Checks
- `/health/video-proxy` - Public health endpoint
- Admin API endpoints for detailed monitoring
- Automatic alerting for system issues

## Future Enhancements

### Potential Improvements
- **Search functionality** within user's generations
- **Tagging system** for better organization
- **Sharing capabilities** with privacy controls
- **Batch operations** (delete multiple, etc.)
- **Export functionality** for user data
- **Analytics dashboard** for usage patterns

### Performance Optimizations
- **CDN integration** for video delivery
- **Thumbnail generation** for faster loading
- **Lazy loading** for large generation lists
- **Caching strategies** for frequently accessed videos

## Troubleshooting

### Common Issues
1. **Videos not loading**: Check proxy URL mapping expiration
2. **Empty generation list**: Verify JWT token and user identification
3. **Slow loading**: Check database indexes and query performance
4. **Network errors**: Verify Qwen service connectivity

### Debug Commands
```bash
# Check database collections
mongo ai_image_generator --eval "db.user_generation_history.find().limit(5)"

# Monitor proxy access logs
tail -f logs/video_proxy.log

# Test API endpoints
curl -H "x-access-token: YOUR_TOKEN" http://localhost:5000/api/user-generations
```
import json
import os
import cv2
import threading
import time
from threading import Event, Lock
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socketserver
import base64

class HologramVideoManager:
    def __init__(self, video_path="videos/hologram.mp4", timestamp_map_path="timestamp_map.json"):
        self.video_path = os.path.abspath(video_path)
        self.timestamp_map = self.load_timestamp_map(timestamp_map_path)
        self.cap = None
        self.is_playing = False
        self.current_mode = "default"
        self.playback_thread = None
        self.stop_event = Event()
        self.video_lock = Lock()
        self.is_speaking = False
        
        # Web server
        self.server = None
        self.server_thread = None
        self.port = 8080
        
        # Video properties
        self.fps = 30
        self.total_frames = 0
        self.frame_width = 640
        self.frame_height = 480
        
        # Video segments (in seconds)
        self.segments = {
            "default": {"start": 0, "end": 12},    # 0-12 seconds: default/walking loop
            "talking": {"start": 13, "end": 19}    # 13-19 seconds: talking loop
        }
        
        # Current frame data for web display
        self.current_frame_data = None
        self.frame_lock = Lock()
        
        # Test video file
        self.use_video = self.test_video_file()
        
        # Start web server
        self.start_web_server()
        
        # Start video processing
        if self.use_video:
            print("Video validated - starting web display")
            self.start_default_video()
        else:
            print("Video unavailable - using animated web display")
            self.start_default_video()

    def load_timestamp_map(self, json_path):
        """Load timestamp mappings from JSON file"""
        try:
            with open(json_path, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            print(f"Warning: Timestamp map not found at {json_path}, using default mappings")
            return {
                "default": 0,
                "talking": 13,
                "greeting": 13,
                "helping": 13,
                "listening": 13,
                "goodbye": 13
            }

    def test_video_file(self):
        """Test if video file can be opened and read"""
        if not os.path.exists(self.video_path):
            print(f"Video file not found: {self.video_path}")
            return False
            
        try:
            test_cap = cv2.VideoCapture(self.video_path)
            if not test_cap.isOpened():
                print("Could not open video file")
                return False
                
            ret, frame = test_cap.read()
            if not ret or frame is None:
                print("Could not read video frames")
                test_cap.release()
                return False
                
            # Get video properties
            self.fps = max(test_cap.get(cv2.CAP_PROP_FPS), 25)
            self.total_frames = int(test_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.frame_width = int(test_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(test_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            test_cap.release()
            
            print(f"Video OK: {self.frame_width}x{self.frame_height}, {self.fps} FPS, {self.total_frames} frames")
            
            # Validate segments
            video_duration = self.total_frames / self.fps
            if video_duration < 19:
                self.segments["talking"]["end"] = min(19, int(video_duration) - 1)
                print(f"Adjusted talking segment to end at {self.segments['talking']['end']}s")
            
            return True
            
        except Exception as e:
            print(f"Error testing video: {e}")
            return False

    def start_web_server(self):
        """Start web server for video display"""
        try:
            # Create HTML file
            self.create_html_page()
            
            # Start server in separate thread
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            
            # Give server time to start
            time.sleep(2)
            
            # Open browser
            url = f"http://localhost:{self.port}/hologram.html"
            print(f"Opening hologram display at: {url}")
            webbrowser.open(url)
            
        except Exception as e:
            print(f"Web server error: {e}")
            print("Falling back to console mode")

    def create_html_page(self):
        """Create HTML page for fullscreen video display only"""
        html_content = '''<!DOCTYPE html>
<html>
<head>
    <title>Laila Hologram</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        html, body {
            height: 100%;
            overflow: hidden;
            background: black;
            cursor: none;
        }
        
        #frame-image {
            width: 100vw;
            height: 100vh;
            object-fit: cover;
            display: block;
        }
    </style>
</head>
<body>
    <img id="frame-image" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAHGbBE9eAAAAABJRU5ErkJggg==" alt="">

    <script>
        function updateFrame() {
            fetch('/frame')
                .then(response => response.text())
                .then(base64Data => {
                    if (base64Data.trim()) {
                        document.getElementById('frame-image').src = 
                            'data:image/jpeg;base64,' + base64Data;
                    }
                })
                .catch(error => {
                    console.error('Frame update error:', error);
                });
        }
        
        // Update display every 33ms (30 FPS)
        setInterval(updateFrame, 33);
        
        // Initial update
        setTimeout(updateFrame, 1000);
        
        // Fullscreen toggle functionality
        function toggleFullscreen() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(err => {
                    console.log('Error attempting to enable fullscreen:', err.message);
                });
            } else {
                document.exitFullscreen();
            }
        }
        
        // Keyboard event handler
        document.addEventListener('keydown', function(event) {
            if (event.key === 'f' || event.key === 'F') {
                event.preventDefault();
                toggleFullscreen();
            } else if (event.key === 'Escape') {
                // ESC will automatically exit fullscreen, no need to handle manually
            }
        });
        
        // Enter fullscreen on click (backup method)
        document.addEventListener('click', function() {
            if (!document.fullscreenElement) {
                toggleFullscreen();
            }
        });
        
        // Auto-enter fullscreen on load
        window.addEventListener('load', function() {
            setTimeout(function() {
                if (document.documentElement.requestFullscreen) {
                    document.documentElement.requestFullscreen().catch(err => {
                        console.log('Auto-fullscreen failed:', err.message);
                    });
                }
            }, 1000);
        });
    </script>
</body>
</html>'''
        
        with open('hologram.html', 'w') as f:
            f.write(html_content)

    def _run_server(self):
        """Run HTTP server"""
        class HologramHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, manager=None, **kwargs):
                self.manager = manager
                super().__init__(*args, **kwargs)
            
            def do_GET(self):
                if self.path == '/status':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    
                    status_data = {
                        'mode': self.manager.current_mode,
                        'status': 'Speaking' if self.manager.is_speaking else 'Idle',
                        'frame': getattr(self.manager, 'current_frame_number', 0),
                        'fps': self.manager.fps
                    }
                    
                    self.wfile.write(json.dumps(status_data).encode())
                    
                elif self.path == '/frame':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    
                    with self.manager.frame_lock:
                        if self.manager.current_frame_data:
                            self.wfile.write(self.manager.current_frame_data)
                        else:
                            self.wfile.write(b'')
                            
                else:
                    super().do_GET()
            
            def log_message(self, format, *args):
                pass  # Suppress server logs
        
        try:
            handler = lambda *args, **kwargs: HologramHandler(*args, manager=self, **kwargs)
            
            with socketserver.TCPServer(("", self.port), handler) as httpd:
                self.server = httpd
                print(f"Web server started on port {self.port}")
                httpd.serve_forever()
                
        except Exception as e:
            print(f"Server error: {e}")

    def start_default_video(self):
        """Start default video segment"""
        self.play_segment("default")

    def play_segment(self, segment_name):
        """Play specific video segment"""
        if segment_name not in self.segments:
            segment_name = "default"
            
        self.stop_video()
        
        print(f"[HOLOGRAM] Switching to segment: {segment_name}")
        self.current_mode = segment_name
        self.stop_event.clear()
        self.is_playing = True
        
        if self.use_video:
            self.playback_thread = threading.Thread(target=self._video_playback_loop, args=(segment_name,), daemon=True)
        else:
            self.playback_thread = threading.Thread(target=self._animated_loop, args=(segment_name,), daemon=True)
            
        self.playback_thread.start()

    def _video_playback_loop(self, segment_name):
        """Video playback loop"""
        cap = None
        
        try:
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                print("Video capture failed - switching to animation")
                self._animated_loop(segment_name)
                return
            
            # Get segment info
            segment = self.segments[segment_name]
            start_frame = int(segment["start"] * self.fps)
            end_frame = min(int(segment["end"] * self.fps), self.total_frames - 1)
            
            current_frame = start_frame
            self.current_frame_number = current_frame
            frame_delay = 1.0 / self.fps
            
            print(f"Playing video segment {segment_name}: frames {start_frame} to {end_frame}")
            
            while self.is_playing and not self.stop_event.is_set():
                try:
                    # Read frame
                    cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
                    ret, frame = cap.read()
                    
                    if not ret or frame is None:
                        current_frame = start_frame
                        continue
                    
                    # Convert frame to base64 for web display
                    self._update_web_frame(frame)
                    self.current_frame_number = current_frame
                    
                    # Next frame
                    current_frame += 1
                    if current_frame >= end_frame:
                        current_frame = start_frame
                    
                    time.sleep(frame_delay)
                    
                except Exception as e:
                    print(f"Video playback error: {e}")
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"Video loop error: {e}")
        finally:
            if cap:
                cap.release()

    def _animated_loop(self, segment_name):
        """Animated display when video unavailable"""
        import numpy as np
        
        frame_count = 0
        
        while self.is_playing and not self.stop_event.is_set():
            try:
                # Create simple animated frame
                height, width = 480, 640
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                
                # Animation based on mode and time
                t = frame_count / 30.0
                
                if segment_name == "talking":
                    # Talking animation - pulsing red/orange
                    intensity = int(128 + 127 * abs(np.sin(t * 8)))
                    color = (intensity//4, intensity//2, intensity)
                else:
                    # Default animation - moving blue/green
                    intensity = int(100 + 100 * abs(np.sin(t * 2)))
                    color = (intensity, intensity//2, intensity//4)
                
                # Draw animated elements
                center_x = int(width//2 + 100 * np.sin(t))
                center_y = int(height//2 + 50 * np.cos(t * 1.5))
                radius = int(50 + 30 * abs(np.sin(t * 4)))
                
                cv2.circle(frame, (center_x, center_y), radius, color, -1)
                cv2.circle(frame, (center_x, center_y), radius + 20, (255, 255, 255), 2)
                
                # Add text
                text = "TALKING" if segment_name == "talking" else "DEFAULT"
                cv2.putText(frame, text, (width//2 - 60, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                
                # Update web display
                self._update_web_frame(frame)
                self.current_frame_number = frame_count
                
                frame_count += 1
                time.sleep(1/30)  # 30 FPS
                
            except Exception as e:
                print(f"Animation error: {e}")
                time.sleep(0.1)

    def _update_web_frame(self, frame):
        """Update frame for web display"""
        try:
            # Encode frame as JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            
            # Convert to base64
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Update shared frame data
            with self.frame_lock:
                self.current_frame_data = frame_base64.encode()
                
        except Exception as e:
            print(f"Frame encoding error: {e}")

    def start_speaking(self):
        """Switch to talking mode"""
        self.is_speaking = True
        print("[HOLOGRAM] AI started speaking")
        self.play_segment("talking")

    def stop_speaking(self):
        """Return to default mode"""
        self.is_speaking = False
        print("[HOLOGRAM] AI finished speaking")
        self.play_segment("default")

    def handle_response(self, response_text):
        """Handle bot response"""
        self.start_speaking()

    def set_listening_mode(self):
        """Set listening mode"""
        if not self.is_speaking:
            self.play_segment("default")

    def stop_video(self):
        """Stop video playback"""
        if self.is_playing:
            self.is_playing = False
            self.stop_event.set()
            
            if self.playback_thread and self.playback_thread.is_alive():
                self.playback_thread.join(timeout=2.0)

    def cleanup(self):
        """Cleanup resources"""
        print("[HOLOGRAM] Cleaning up...")
        self.stop_video()
        
        if self.server:
            try:
                self.server.shutdown()
            except:
                pass
        
        # Clean up HTML file
        try:
            os.remove('hologram.html')
        except:
            pass

    def __del__(self):
        self.cleanup()

# For backward compatibility
def play_hologram_video():
    manager = HologramVideoManager()
    return manager
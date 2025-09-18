import os
import re
import speech_recognition as sr
from gtts import gTTS
from playsound import playsound
import cv2
import threading
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor

from chatbot import get_bot_response
from video_manager import HologramVideoManager

TTS_LANGUAGE = "en"
SILENCE_TIMEOUT = 15  # Return to default video after 15 seconds of silence

class HologramChatbot:
    def __init__(self):
        print("Initializing Always-Listening Hologram Chatbot...")
        
        try:
            self.video_manager = HologramVideoManager()
        except Exception as e:
            print(f"Video manager error: {e}")
            self.video_manager = None
        
        self.is_listening = True
        self.last_speech_time = time.time()
        self.is_currently_speaking = False
        self.speaking_lock = threading.Lock()
        
        # Pre-initialize recognizer for faster recognition
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        
        # Optimized recognizer settings for continuous listening
        self.recognizer.energy_threshold = 3500
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.pause_threshold = 0.8  # Slightly longer pause for natural speech
        self.recognizer.phrase_threshold = 0.3
        self.recognizer.non_speaking_duration = 0.5
        
        # Quick microphone setup
        print("Setting up microphone...")
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
        except Exception as e:
            print(f"Microphone setup warning: {e}")
        
        # Thread executor for parallel processing
        self.executor = ThreadPoolExecutor(max_workers=3)
        
        # Start silence monitor thread
        self.silence_monitor_thread = threading.Thread(target=self.monitor_silence, daemon=True)
        self.silence_monitor_thread.start()
        
        print("Chatbot ready - Always listening!")

    def clean_response_text(self, text):
        """Remove symbols, asterisks, and unwanted characters from response"""
        if not text:
            return ""
        
        # Remove asterisks and content between them (actions/emotes)
        text = re.sub(r'\*[^*]*\*', '', text)
        
        # Remove markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold**
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # *italic*
        text = re.sub(r'__([^_]+)__', r'\1', text)      # __bold__
        text = re.sub(r'_([^_]+)_', r'\1', text)        # _italic_
        text = re.sub(r'~~([^~]+)~~', r'\1', text)      # ~~strikethrough~~
        
        # Remove emojis and special unicode characters
        text = re.sub(r'[^\w\s.,!?;:\'-]', '', text)
        
        # Remove unwanted symbols but keep punctuation
        text = re.sub(r'[#@$%^&*(){}[\]<>+=|\\~`"]', '', text)
        
        # Clean up multiple spaces and line breaks
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Remove any remaining double spaces
        while '  ' in text:
            text = text.replace('  ', ' ')
        
        return text

    def speak_response_synchronized(self, text):
        """Synchronized TTS with video - ensures perfect timing"""
        # Clean text before speaking
        clean_text = self.clean_response_text(text)
        
        if not clean_text:
            return
            
        print(f"Laila: {clean_text}")
        
        with self.speaking_lock:
            self.is_currently_speaking = True
            
            try:
                # Start talking video BEFORE generating TTS
                if self.video_manager:
                    print("[SYNC] Starting talking video...")
                    self.video_manager.start_speaking()
                
                # Small delay to ensure video starts
                time.sleep(0.1)
                
                # Create temporary file
                temp_fd, temp_filename = tempfile.mkstemp(suffix='.mp3')
                os.close(temp_fd)
                
                # Generate TTS
                print("[SYNC] Generating TTS...")
                tts = gTTS(text=clean_text, lang=TTS_LANGUAGE, slow=False, tld='com')
                tts.save(temp_filename)
                
                # Play TTS audio
                print("[SYNC] Playing TTS audio...")
                playsound(temp_filename)
                
                # Audio finished - stop talking video
                print("[SYNC] Audio finished - stopping talking video...")
                if self.video_manager:
                    self.video_manager.stop_speaking()
                
                # Cleanup
                try:
                    os.unlink(temp_filename)
                except:
                    pass
                    
            except Exception as e:
                print(f"TTS error: {e}")
                # Ensure video stops even on error
                if self.video_manager:
                    self.video_manager.stop_speaking()
            finally:
                self.is_currently_speaking = False
                # Update last speech time after speaking
                self.last_speech_time = time.time()

    def listen_for_speech(self, timeout=2.0, phrase_limit=8):
        """Listen for speech with reasonable timeout"""
        try:
            with self.microphone as source:
                audio = self.recognizer.listen(
                    source, 
                    timeout=timeout, 
                    phrase_time_limit=phrase_limit
                )
                return audio
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            print(f"Listening error: {e}")
            return None

    def recognize_speech(self, audio):
        """Convert audio to text"""
        if not audio:
            return ""
        
        try:
            return self.recognizer.recognize_google(audio, language='en-US').strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print(f"Speech recognition error: {e}")
            return ""
        except Exception as e:
            print(f"Recognition error: {e}")
            return ""

    def is_question_or_command(self, text):
        """Check if text appears to be a question or command"""
        if not text:
            return False
        
        text_lower = text.lower().strip()
        
        # Filter out very short or meaningless phrases
        if len(text_lower) < 3:
            return False
        
        # Common noise words to ignore
        noise_words = ['um', 'uh', 'hmm', 'ah', 'oh', 'hey', 'hi', 'hello']
        if text_lower in noise_words:
            return False
        
        # Question indicators
        question_words = ['what', 'how', 'why', 'when', 'where', 'who', 'which', 'can', 'could', 
                         'will', 'would', 'should', 'is', 'are', 'do', 'does', 'did', 'tell', 'explain']
        
        # Command indicators
        command_words = ['play', 'show', 'find', 'search', 'calculate', 'help', 'stop', 'start', 
                        'open', 'close', 'turn', 'set', 'get', 'make', 'create', 'give']
        
        # Check for question marks
        if '?' in text:
            return True
        
        # Check if starts with question/command words
        words = text_lower.split()
        if words and (words[0] in question_words or words[0] in command_words):
            return True
        
        # Check if contains question/command words
        if any(word in words for word in question_words + command_words):
            return True
        
        # If it's a longer phrase (likely intentional speech)
        if len(words) >= 3:
            return True
        
        return False

    def process_speech(self, text):
        """Process recognized speech with synchronized audio/video"""
        print(f"Processing: '{text}'")
        
        # Wait if currently speaking to avoid interruption
        while self.is_currently_speaking:
            time.sleep(0.1)
        
        # Update last speech time
        self.last_speech_time = time.time()
        
        try:
            # Get AI response first (before any video changes)
            print("[SYNC] Getting AI response...")
            bot_response = get_bot_response(text)
            
            # Now do synchronized TTS + video
            print("[SYNC] Starting synchronized response...")
            self.speak_response_synchronized(bot_response)
            
        except Exception as e:
            print(f"Processing error: {e}")
            self.speak_response_synchronized("Sorry, I had trouble processing that.")

    def monitor_silence(self):
        """Monitor for silence and return to default video after timeout"""
        while self.is_listening:
            try:
                current_time = time.time()
                time_since_speech = current_time - self.last_speech_time
                
                # Only check for silence timeout if not currently speaking
                if not self.is_currently_speaking and time_since_speech >= SILENCE_TIMEOUT:
                    if self.video_manager and self.video_manager.current_mode != "default":
                        print(f"[SILENCE MONITOR] {SILENCE_TIMEOUT}s of silence - returning to default video")
                        self.video_manager.play_segment("default")
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                print(f"Silence monitor error: {e}")
                time.sleep(5)

    def continuous_listening_loop(self):
        """Main continuous listening loop"""
        print("Starting continuous listening mode...")
        print(f"Will return to default video after {SILENCE_TIMEOUT} seconds of silence")
        print("Speak naturally - no trigger words needed!")
        
        consecutive_empty = 0
        max_consecutive_empty = 10  # Reset after too many empty recognitions
        
        while self.is_listening:
            try:
                # Skip listening if currently speaking to avoid feedback
                if self.is_currently_speaking:
                    time.sleep(0.5)
                    continue
                
                # Listen for speech
                audio = self.listen_for_speech(timeout=1.0, phrase_limit=10)
                
                if audio:
                    text = self.recognize_speech(audio)
                    
                    if text:
                        consecutive_empty = 0
                        print(f"Heard: '{text}'")
                        
                        # Check if it's a valid question or command
                        if self.is_question_or_command(text):
                            print("Valid question/command detected!")
                            # Process synchronously to maintain proper audio/video sync
                            self.process_speech(text)
                        else:
                            print("Not recognized as question/command - ignoring")
                    else:
                        consecutive_empty += 1
                else:
                    consecutive_empty += 1
                
                # Reset microphone if too many consecutive empty results
                if consecutive_empty >= max_consecutive_empty:
                    print("Resetting audio system...")
                    consecutive_empty = 0
                    time.sleep(1)
                    try:
                        with self.microphone as source:
                            self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    except:
                        pass
                
                # Small delay to prevent excessive CPU usage
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                print("\nShutting down...")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                time.sleep(1)

    def run(self):
        """Main execution loop"""
        print("=" * 60)
        print("SYNCHRONIZED ALWAYS-LISTENING LAILA HOLOGRAM SYSTEM")
        print("=" * 60)
        print("• Microphone is always active - no trigger words needed")
        print("• Ask questions naturally or give commands")
        print(f"• Returns to default video after {SILENCE_TIMEOUT}s of silence")
        print("• Audio and video are perfectly synchronized")
        print("• Text is automatically cleaned (no symbols spoken)")
        print("• Press Ctrl+C to exit")
        print("=" * 60)
        
        try:
            self.continuous_listening_loop()
        except KeyboardInterrupt:
            print("\nShutdown requested...")
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources"""
        print("Cleaning up...")
        self.is_listening = False
        
        # Shutdown executor
        self.executor.shutdown(wait=False)
        
        # Cleanup video manager
        if self.video_manager:
            try:
                self.video_manager.cleanup()
            except:
                pass
        
        print("Goodbye!")

def main():
    try:
        chatbot = HologramChatbot()
        chatbot.run()
    except Exception as e:
        print(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
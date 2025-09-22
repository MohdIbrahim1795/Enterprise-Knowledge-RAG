#!/usr/bin/env python3
"""
Python GUI Client for RAG Chatbot using tkinter
Provides a desktop application interface for the RAG system
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import threading
import json
import requests
from datetime import datetime
from typing import Optional, Dict, Any
import queue


class RAGGUIClient:
    """GUI client for RAG chatbot using tkinter"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("RAG Chatbot - Desktop Client")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        # Configuration
        self.api_url = "http://localhost:8000"
        self.timeout = 30
        self.conversation_id: Optional[str] = None
        self.session = requests.Session()
        
        # Message queue for thread communication
        self.message_queue = queue.Queue()
        
        # Setup GUI
        self.setup_gui()
        self.setup_session()
        
        # Start checking message queue
        self.check_message_queue()
        
        # Initial health check
        self.check_health()
    
    def setup_gui(self):
        """Setup the GUI components"""
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="🤖 RAG Chatbot", 
            font=("Arial", 16, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))
        
        # Chat display area
        self.chat_display = scrolledtext.ScrolledText(
            main_frame,
            wrap=tk.WORD,
            width=70,
            height=20,
            state=tk.DISABLED,
            font=("Arial", 10)
        )
        self.chat_display.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # Configure text tags for styling
        self.chat_display.tag_configure("user", foreground="blue", font=("Arial", 10, "bold"))
        self.chat_display.tag_configure("assistant", foreground="darkgreen")
        self.chat_display.tag_configure("error", foreground="red")
        self.chat_display.tag_configure("info", foreground="gray", font=("Arial", 9, "italic"))
        self.chat_display.tag_configure("source", foreground="purple", font=("Arial", 9))
        
        # Input frame
        input_frame = ttk.Frame(main_frame)
        input_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)
        
        # Query input
        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(
            input_frame,
            textvariable=self.query_var,
            font=("Arial", 10),
            width=50
        )
        self.query_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        self.query_entry.bind("<Return>", self.send_query_event)
        
        # Send button
        self.send_button = ttk.Button(
            input_frame,
            text="Send",
            command=self.send_query_thread
        )
        self.send_button.grid(row=0, column=1)
        
        # Control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E))
        
        # Buttons
        ttk.Button(
            control_frame,
            text="Clear Chat",
            command=self.clear_chat
        ).grid(row=0, column=0, padx=(0, 5))
        
        ttk.Button(
            control_frame,
            text="New Conversation",
            command=self.new_conversation
        ).grid(row=0, column=1, padx=(0, 5))
        
        ttk.Button(
            control_frame,
            text="Settings",
            command=self.show_settings
        ).grid(row=0, column=2, padx=(0, 5))
        
        ttk.Button(
            control_frame,
            text="Health Check",
            command=self.check_health
        ).grid(row=0, column=3, padx=(0, 5))
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            font=("Arial", 9)
        )
        status_bar.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Focus on input
        self.query_entry.focus()
    
    def setup_session(self):
        """Setup HTTP session"""
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'RAG-GUI-Client/1.0'
        })
    
    def append_to_chat(self, message: str, tag: str = None):
        """Append message to chat display"""
        self.chat_display.config(state=tk.NORMAL)
        
        # Add timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_display.insert(tk.END, f"[{timestamp}] ", "info")
        
        # Add message
        if tag:
            self.chat_display.insert(tk.END, message + "\n\n", tag)
        else:
            self.chat_display.insert(tk.END, message + "\n\n")
        
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
    
    def send_query_event(self, event=None):
        """Handle Enter key press"""
        self.send_query_thread()
    
    def send_query_thread(self):
        """Send query in separate thread to avoid blocking GUI"""
        query = self.query_var.get().strip()
        if not query:
            return
        
        # Clear input and disable controls
        self.query_var.set("")
        self.send_button.config(state=tk.DISABLED)
        self.query_entry.config(state=tk.DISABLED)
        
        # Update status
        self.status_var.set("Processing query...")
        
        # Add user message to chat
        self.append_to_chat(f"👤 You: {query}", "user")
        
        # Start background thread
        thread = threading.Thread(
            target=self.send_query_background,
            args=(query,),
            daemon=True
        )
        thread.start()
    
    def send_query_background(self, query: str):
        """Send query to API in background thread"""
        try:
            payload = {
                "query": query,
                "max_results": 3
            }
            
            if self.conversation_id:
                payload["conversation_id"] = self.conversation_id
            
            response = self.session.post(
                f"{self.api_url}/chat",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                self.conversation_id = data.get("conversation_id")
                self.message_queue.put(("success", data))
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                self.message_queue.put(("error", error_msg))
                
        except requests.RequestException as e:
            self.message_queue.put(("error", f"Request failed: {str(e)}"))
        except Exception as e:
            self.message_queue.put(("error", f"Unexpected error: {str(e)}"))
    
    def check_message_queue(self):
        """Check for messages from background threads"""
        try:
            while True:
                message_type, data = self.message_queue.get_nowait()
                
                if message_type == "success":
                    self.handle_successful_response(data)
                elif message_type == "error":
                    self.handle_error_response(data)
                elif message_type == "health":
                    self.handle_health_response(data)
                    
        except queue.Empty:
            pass
        
        # Re-enable controls
        self.send_button.config(state=tk.NORMAL)
        self.query_entry.config(state=tk.NORMAL)
        self.query_entry.focus()
        
        # Update status
        conv_info = f" (Conv: {self.conversation_id[:8]}...)" if self.conversation_id else ""
        self.status_var.set(f"Ready{conv_info}")
        
        # Schedule next check
        self.root.after(100, self.check_message_queue)
    
    def handle_successful_response(self, data: Dict[str, Any]):
        """Handle successful API response"""
        # Add assistant response
        answer = data.get("answer", "No answer provided")
        self.append_to_chat(f"🤖 Assistant: {answer}", "assistant")
        
        # Add sources if available
        sources = data.get("sources", [])
        if sources:
            sources_text = "📚 Sources:\n"
            for i, source in enumerate(sources[:3], 1):
                source_name = source.get("source", "Unknown")
                score = source.get("score", 0)
                page = source.get("page")
                page_info = f" (page {page})" if page else ""
                sources_text += f"  {i}. {source_name}{page_info} - Relevance: {score:.2f}\n"
            
            self.append_to_chat(sources_text.strip(), "source")
        
        # Add processing time
        processing_time = data.get("processing_time")
        if processing_time:
            time_info = f"⏱️ Processing time: {processing_time:.2f}s"
            if data.get("cached"):
                time_info += " (cached)"
            self.append_to_chat(time_info, "info")
    
    def handle_error_response(self, error_msg: str):
        """Handle error response"""
        self.append_to_chat(f"❌ Error: {error_msg}", "error")
    
    def handle_health_response(self, is_healthy: bool):
        """Handle health check response"""
        if is_healthy:
            messagebox.showinfo("Health Check", "✅ Service is healthy and responding")
        else:
            messagebox.showerror("Health Check", f"❌ Service is not responding\nURL: {self.api_url}")
    
    def clear_chat(self):
        """Clear chat display"""
        if messagebox.askyesno("Clear Chat", "Clear all messages from the chat?"):
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete(1.0, tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.append_to_chat("Chat cleared", "info")
    
    def new_conversation(self):
        """Start new conversation"""
        if messagebox.askyesno("New Conversation", "Start a new conversation? (This will clear conversation context)"):
            self.conversation_id = None
            self.append_to_chat("🔄 Started new conversation", "info")
    
    def show_settings(self):
        """Show settings dialog"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("400x300")
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # Center the window
        settings_window.update_idletasks()
        x = (settings_window.winfo_screenwidth() // 2) - (400 // 2)
        y = (settings_window.winfo_screenheight() // 2) - (300 // 2)
        settings_window.geometry(f"400x300+{x}+{y}")
        
        frame = ttk.Frame(settings_window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # API URL setting
        ttk.Label(frame, text="API URL:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        api_url_var = tk.StringVar(value=self.api_url)
        ttk.Entry(frame, textvariable=api_url_var, width=40).grid(row=0, column=1, pady=(0, 5))
        
        # Timeout setting
        ttk.Label(frame, text="Timeout (seconds):").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        timeout_var = tk.StringVar(value=str(self.timeout))
        ttk.Entry(frame, textvariable=timeout_var, width=10).grid(row=1, column=1, sticky=tk.W, pady=(0, 5))
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(20, 0))
        
        def save_settings():
            try:
                self.api_url = api_url_var.get().rstrip('/')
                self.timeout = int(timeout_var.get())
                messagebox.showinfo("Settings", "Settings saved successfully")
                settings_window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid timeout value")
        
        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Cancel", command=settings_window.destroy).pack(side=tk.LEFT)
    
    def check_health(self):
        """Check service health"""
        self.status_var.set("Checking health...")
        
        def health_check_background():
            try:
                response = self.session.get(
                    f"{self.api_url}/health",
                    timeout=self.timeout
                )
                is_healthy = response.status_code == 200
                self.message_queue.put(("health", is_healthy))
            except requests.RequestException:
                self.message_queue.put(("health", False))
        
        thread = threading.Thread(target=health_check_background, daemon=True)
        thread.start()
    
    def on_closing(self):
        """Handle window closing"""
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.root.quit()
            self.root.destroy()


def main():
    """Main GUI application entry point"""
    root = tk.Tk()
    app = RAGGUIClient(root)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Start GUI event loop
    root.mainloop()


if __name__ == "__main__":
    main()
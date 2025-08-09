# app.py - Production-ready with ALL performance optimizations
from flask import Flask, request, render_template, send_file, jsonify, redirect
from werkzeug.utils import secure_filename
import os
import uuid
import logging
import base64
from datetime import datetime
import gc  # For memory cleanup
from concurrent.futures import ThreadPoolExecutor
import threading
import queue

# Method 1: Use pypdf instead of PyPDF2 for better performance
try:
    import pypdf  # Faster than PyPDF2
    PDF_LIBRARY = 'pypdf'
except ImportError:
    import PyPDF2 as pypdf  # Fallback
    PDF_LIBRARY = 'PyPDF2'

# Try PyMuPDF for optimized thumbnails
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

app = Flask(__name__)

# Production Configuration
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-production-secret'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    UPLOAD_FOLDER = 'temp_uploads'
    # Render-specific optimizations
    MAX_WORKERS = 1 if os.environ.get('RENDER') else 2
    THUMBNAIL_QUALITY = 'low' if os.environ.get('RENDER') else 'high'

app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'pdf'}

# Global storage for sessions and merged PDFs
session_files = {}
merged_pdfs = {}

# Method 2: Implement Async Processing with ThreadPoolExecutor
pdf_executor = ThreadPoolExecutor(max_workers=app.config['MAX_WORKERS'])
processing_queue = queue.Queue()

def async_worker():
    """Background worker for async processing"""
    while True:
        try:
            task = processing_queue.get(timeout=1)
            if task is None:
                break
            task['function'](**task['args'])
            processing_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Async processing error: {e}")

# Start background worker
worker_thread = threading.Thread(target=async_worker, daemon=True)
worker_thread.start()

# Method 3: Security headers and HTTPS enforcement
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    if not app.debug:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

@app.before_request
def force_https():
    if (not request.is_secure and not app.debug and 
        request.headers.get('X-Forwarded-Proto') != 'https'):
        return redirect(request.url.replace('http://', 'https://'), code=301)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Method 4: Optimized Thumbnail Generation
def get_placeholder_thumbnail():
    """Lightweight placeholder SVG - much faster than generating real thumbnails"""
    return "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEyMCIgdmlld0JveD0iMCAwIDEwMCAxMjAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMjAiIGZpbGw9IiNGNUY1RjUiLz48dGV4dCB4PSI1MCIgeT0iNzAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+UERGPC90ZXh0Pjwvc3ZnPg=="

def generate_pdf_thumbnail_fast(pdf_path):
    """Optimized thumbnail generation - Method 4"""
    if not FITZ_AVAILABLE:
        return get_placeholder_thumbnail()
    
    try:
        pdf_document = fitz.open(pdf_path)
        if len(pdf_document) == 0:
            pdf_document.close()
            return get_placeholder_thumbnail()
        
        first_page = pdf_document[0]
        
        # Ultra-fast rendering with minimal quality
        scale = 0.3 if app.config['THUMBNAIL_QUALITY'] == 'low' else 0.5
        mat = fitz.Matrix(scale, scale)
        pix = first_page.get_pixmap(matrix=mat, alpha=False)  # No alpha channel
        img_data = pix.tobytes("png")
        pdf_document.close()
        
        # Convert to base64
        img_base64 = base64.b64encode(img_data).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"
        
    except Exception as e:
        logger.error(f"Fast thumbnail error: {str(e)}")
        return get_placeholder_thumbnail()

def generate_thumbnail_async(session_id, file_index, file_path):
    """Background thumbnail generation"""
    try:
        thumbnail = generate_pdf_thumbnail_fast(file_path)
        # Update session files with real thumbnail
        if session_id in session_files:
            for file_info in session_files[session_id]:
                if file_info['file_index'] == file_index:
                    file_info['thumbnail'] = thumbnail
                    break
        logger.debug(f"Generated thumbnail for session {session_id}, file {file_index}")
    except Exception as e:
        logger.error(f"Async thumbnail generation error: {e}")

# Method 5: Memory cleanup and session management
def cleanup_memory():
    """Aggressive memory cleanup for Render free tier"""
    try:
        gc.collect()  # Force garbage collection
        
        # Clean old sessions (older than 10 minutes)
        current_time = datetime.now()
        expired_sessions = []
        
        for session_id in list(session_files.keys()):
            # Simple age check based on session creation
            try:
                session_age = current_time - datetime.fromtimestamp(
                    os.path.getctime(os.path.join(app.config['UPLOAD_FOLDER'], session_id))
                )
                if session_age.seconds > 600:  # 10 minutes
                    expired_sessions.append(session_id)
            except:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            cleanup_session(session_id)
            
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
        
    except Exception as e:
        logger.error(f"Memory cleanup error: {e}")

def cleanup_session(session_id):
    """Clean up session files and directories"""
    try:
        # Remove from memory
        if session_id in session_files:
            del session_files[session_id]
        
        if session_id in merged_pdfs:
            del merged_pdfs[session_id]
        
        # Remove files from disk
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)
            
    except Exception as e:
        logger.error(f"Session cleanup error for {session_id}: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload-preview', methods=['POST'])
def upload_preview():
    """Optimized upload with minimal processing - Method 1 & 4"""
    try:
        # Periodic cleanup
        if len(session_files) > 50:  # Cleanup when too many sessions
            cleanup_memory()
        
        if 'pdf_files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400
        
        files = request.files.getlist('pdf_files')
        
        if not files or (len(files) == 1 and files[0].filename == ''):
            return jsonify({'error': 'No files selected'}), 400
        
        # Session management
        session_id = request.form.get('existing_session')
        if session_id and session_id in session_files:
            file_index = len(session_files[session_id])
        else:
            session_id = str(uuid.uuid4())
            file_index = 0
            
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        os.makedirs(temp_dir, exist_ok=True)
        
        if session_id not in session_files:
            session_files[session_id] = []
        
        previews = []
        
        for file in files:
            if not file or file.filename == '':
                continue
                
            if not allowed_file(file.filename):
                logger.warning(f"Invalid file type: {file.filename}")
                continue
            
            # Quick file save
            safe_name = secure_filename(file.filename)
            filename = f"{file_index}_{safe_name}"
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)
            
            # Get basic info quickly
            file_size = os.path.getsize(file_path)
            
            # Use placeholder thumbnail for immediate response
            thumbnail = get_placeholder_thumbnail()
            
            # Quick page count with error handling
            try:
                with open(file_path, 'rb') as pdf_file:
                    if PDF_LIBRARY == 'pypdf':
                        reader = pypdf.PdfReader(pdf_file, strict=False)
                    else:
                        reader = pypdf.PdfFileReader(pdf_file, strict=False)
                    page_count = len(reader.pages)
            except Exception:
                page_count = 1  # Default assumption for speed
            
            file_info = {
                'id': f"{session_id}_{file_index}",
                'filename': file.filename,
                'safe_filename': filename,
                'size': file_size,
                'pages': page_count,
                'thumbnail': thumbnail,  # Placeholder for speed
                'session_id': session_id,
                'file_index': file_index,
                'file_path': filename
            }
            
            session_files[session_id].append(file_info)
            previews.append(file_info)
            
            # Queue thumbnail generation for background processing
            processing_queue.put({
                'function': generate_thumbnail_async,
                'args': {
                    'session_id': session_id,
                    'file_index': file_index,
                    'file_path': file_path
                }
            })
            
            file_index += 1
        
        return jsonify({
            'success': True,
            'previews': previews,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/merge-ordered', methods=['POST'])
def merge_ordered_pdfs():
    """Optimized PDF merging with pypdf - Method 1"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        file_order = data.get('file_order', [])
        
        logger.info(f"Merge request for session {session_id} with {len(file_order)} files")
        
        if not session_id or not file_order:
            return jsonify({'error': 'Missing session or file order data'}), 400
        
        if len(file_order) < 1:
            return jsonify({'error': 'Please select at least 1 PDF file'}), 400
        
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        
        if not os.path.exists(temp_dir):
            return jsonify({'error': 'Session expired or invalid'}), 400
        
        session_file_list = session_files.get(session_id, [])
        if not session_file_list:
            return jsonify({'error': 'No files found in session'}), 400
        
        # Use pypdf for better performance
        if PDF_LIBRARY == 'pypdf':
            merger = pypdf.PdfWriter()
        else:
            merger = pypdf.PdfFileMerger()
            
        processed_files = []
        
        # Process files in the specified order
        for order_index, file_info in enumerate(file_order):
            file_id = file_info.get('id')
            original_filename = file_info.get('filename')
            
            # Find the file in session
            session_file = None
            for sf in session_file_list:
                if sf['id'] == file_id:
                    session_file = sf
                    break
            
            if not session_file:
                logger.warning(f"File {file_id} not found in session")
                continue
            
            file_path = os.path.join(temp_dir, session_file['safe_filename'])
            
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                continue
            
            # Optimized PDF processing
            try:
                with open(file_path, 'rb') as pdf_file:
                    if PDF_LIBRARY == 'pypdf':
                        pdf_reader = pypdf.PdfReader(pdf_file, strict=False)
                        page_count = len(pdf_reader.pages)
                        
                        # Add each page
                        for page in pdf_reader.pages:
                            merger.add_page(page)
                    else:
                        pdf_reader = pypdf.PdfFileReader(pdf_file, strict=False)
                        page_count = pdf_reader.getNumPages()
                        merger.append(pdf_file)
                    
                    processed_files.append({
                        'filename': original_filename,
                        'pages': page_count
                    })
                    
                logger.info(f"Successfully added {page_count} pages from {original_filename}")
                
            except Exception as e:
                logger.error(f"Error processing {file_path}: {str(e)}")
                continue
        
        if not processed_files:
            return jsonify({'error': 'No valid files could be processed'}), 400
        
        # Create output file
        total_pages = sum(f['pages'] for f in processed_files)
        if len(processed_files) == 1:
            output_filename = f"processed_{processed_files[0]['filename'].replace('.pdf', '')}_{datetime.now().strftime('%H%M%S')}.pdf"
        else:
            output_filename = f"merged_{len(processed_files)}_files_{total_pages}_pages_{datetime.now().strftime('%H%M%S')}.pdf"
        
        output_path = os.path.join(temp_dir, output_filename)
        
        # Write the merged PDF
        with open(output_path, 'wb') as output_file:
            if PDF_LIBRARY == 'pypdf':
                merger.write(output_file)
            else:
                merger.write(output_file)
        
        # Close the merger
        if hasattr(merger, 'close'):
            merger.close()
        
        # Store merged PDF info
        merged_id = str(uuid.uuid4())
        merged_pdfs[merged_id] = {
            'path': output_path,
            'filename': output_filename,
            'session_id': session_id,
            'created_at': datetime.now(),
            'file_count': len(processed_files),
            'total_pages': total_pages
        }
        
        logger.info(f"Successfully merged {len(processed_files)} PDFs with {total_pages} total pages")
        
        # Cleanup memory after merge
        cleanup_memory()
        
        return jsonify({
            'success': True,
            'merged_id': merged_id,
            'filename': output_filename,
            'file_count': len(processed_files),
            'total_pages': total_pages,
            'message': f'Successfully merged {len(processed_files)} PDF(s) with {total_pages} pages'
        })
        
    except Exception as e:
        logger.error(f"Error in merge_ordered_pdfs: {str(e)}")
        return jsonify({'error': f'An error occurred while processing PDFs: {str(e)}'}), 500

@app.route('/download-merged/<merged_id>')
def download_merged_pdf(merged_id):
    """Download merged PDF with custom filename support"""
    try:
        if merged_id not in merged_pdfs:
            return jsonify({'error': 'Merged PDF not found or expired'}), 404
        
        merged_info = merged_pdfs[merged_id]
        output_path = merged_info['path']
        original_filename = merged_info['filename']
        
        # Get custom filename from query parameter
        custom_filename = request.args.get('filename')
        
        if custom_filename:
            if not custom_filename.lower().endswith('.pdf'):
                custom_filename += '.pdf'
            download_filename = secure_filename(custom_filename)
            if not download_filename or download_filename == '.pdf':
                download_filename = original_filename
        else:
            download_filename = original_filename
        
        if not os.path.exists(output_path):
            return jsonify({'error': 'File not found on server'}), 404
        
        logger.info(f"Downloading: {download_filename}")
        
        return send_file(
            output_path,
            as_attachment=True,
            download_name=download_filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': 'Error downloading file'}), 500

@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'pdf_library': PDF_LIBRARY,
        'sessions': len(session_files),
        'merged_files': len(merged_pdfs)
    })

# Startup optimization for production
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    logger.info(f"Starting PDF Merger Pro with {PDF_LIBRARY}")
    logger.info(f"PyMuPDF available: {FITZ_AVAILABLE}")
    logger.info(f"Max workers: {app.config['MAX_WORKERS']}")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

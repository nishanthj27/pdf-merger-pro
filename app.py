# app.py - Production-ready version for deployment
from flask import Flask, request, render_template, send_file, jsonify, redirect
from werkzeug.utils import secure_filename
import pypdf
import os
import uuid
from datetime import datetime
import logging
import base64

# Fix PyMuPDF import
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    print("PyMuPDF not available. Thumbnails will be disabled.")
    FITZ_AVAILABLE = False

# Production Configuration Class
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here-change-in-production'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    UPLOAD_FOLDER = 'temp_uploads'

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_pdf_thumbnail(pdf_path):
    """Generate thumbnail for PDF first page"""
    if not FITZ_AVAILABLE:
        logger.warning("PyMuPDF not available, returning placeholder thumbnail")
        return "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTUwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDE1MCAyNDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxNTAiIGhlaWdodD0iMTgwIiBmaWxsPSIjRjVGNUY1Ii8+CjxwYXRoIGQ9Ik0zMCA0MEgxMjBWMTQwSDMwVjQwWiIgZmlsbD0iI0U1RTVFNSIvPgo8dGV4dCB4PSI3NSIgeT0iMTAwIiBmb250LWZhbWlseT0iQXJpYWwsIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPlBERjwvdGV4dD4KPC9zdmc+"
    
    try:
        # Open PDF with PyMuPDF
        pdf_document = fitz.open(pdf_path)
        if len(pdf_document) == 0:
            pdf_document.close()
            return None
            
        first_page = pdf_document[0]
        
        # Render page to image with smaller size for thumbnail
        mat = fitz.Matrix(0.8, 0.8)  # Smaller scale for thumbnails
        pix = first_page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        
        # Convert to base64 for web display
        img_base64 = base64.b64encode(img_data).decode('utf-8')
        pdf_document.close()
        
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        logger.error(f"Error generating thumbnail for {pdf_path}: {str(e)}")
        # Return a placeholder thumbnail
        return "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTUwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDE1MCAyNDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxNTAiIGhlaWdodD0iMTgwIiBmaWxsPSIjRjVGNUY1Ii8+CjxwYXRoIGQ9Ik0zMCA0MEgxMjBWMTQwSDMwVjQwWiIgZmlsbD0iI0U1RTVFNSIvPgo8dGV4dCB4PSI3NSIgeT0iMTAwIiBmb250LWZhbWlseT0iQXJpYWwsIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPlBERjwvdGV4dD4KPC9zdmc+"

# Global storage for session files and merged PDFs
session_files = {}
merged_pdfs = {}  # Store merged PDF info for download

# Security headers for production
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# Force HTTPS in production
@app.before_request
def force_https():
    if not request.is_secure and not app.debug and request.headers.get('X-Forwarded-Proto') != 'https':
        return redirect(request.url.replace('http://', 'https://'), code=301)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload-preview', methods=['POST'])
def upload_preview():
    """Upload files and return preview data"""
    try:
        if 'pdf_files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400
        
        files = request.files.getlist('pdf_files')
        
        if not files or (len(files) == 1 and files[0].filename == ''):
            return jsonify({'error': 'No files selected'}), 400
        
        # Create unique session ID
        session_id = str(uuid.uuid4())
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        os.makedirs(temp_dir, exist_ok=True)
        
        # Initialize session storage
        if session_id not in session_files:
            session_files[session_id] = []
        
        previews = []
        
        # Get current file index (for adding more files to existing session)
        existing_session = request.form.get('existing_session')
        if existing_session and existing_session in session_files:
            session_id = existing_session
            temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
            file_index = len(session_files[session_id])
        else:
            file_index = 0
        
        for file in files:
            if not file or file.filename == '':
                continue
                
            if not allowed_file(file.filename):
                logger.warning(f"Invalid file type: {file.filename}")
                continue
            
            # Create safe filename
            safe_original_name = secure_filename(file.filename)
            filename = f"{file_index}_{safe_original_name}"
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)
            
            logger.info(f"Saved file: {filename} to {file_path}")
            
            # Generate thumbnail
            thumbnail = generate_pdf_thumbnail(file_path)
            
            # Get PDF info
            try:
                with open(file_path, 'rb') as pdf_file:
                    pdf_reader = pypdf.PdfReader(pdf_file)
                    page_count = len(pdf_reader.pages)
            except Exception as e:
                logger.error(f"Error reading PDF {file.filename}: {str(e)}")
                page_count = 0
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            file_info = {
                'id': f"{session_id}_{file_index}",
                'filename': file.filename,
                'safe_filename': filename,
                'size': file_size,
                'pages': page_count,
                'thumbnail': thumbnail,
                'session_id': session_id,
                'file_index': file_index,
                'file_path': filename
            }
            
            # Store in session
            session_files[session_id].append(file_info)
            previews.append(file_info)
            
            logger.info(f"Processed file: {file.filename} -> {filename} with {page_count} pages")
            file_index += 1
        
        if not previews:
            return jsonify({'error': 'No valid PDF files found'}), 400
        
        logger.info(f"Session {session_id} now has {len(session_files[session_id])} files")
        
        return jsonify({
            'success': True,
            'previews': previews,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Error in upload_preview: {str(e)}")
        return jsonify({'error': f'Error processing files: {str(e)}'}), 500

@app.route('/merge-ordered', methods=['POST'])
def merge_ordered_pdfs():
    """Merge PDFs in specified order - Returns merge info instead of file"""
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
        
        # Get session files
        session_file_list = session_files.get(session_id, [])
        if not session_file_list:
            return jsonify({'error': 'No files found in session'}), 400
        
        logger.info(f"Session has {len(session_file_list)} files available")
        
        # Create merger object
        merger = pypdf.PdfWriter()
        processed_files = []
        
        # Process files in the specified order
        for order_index, file_info in enumerate(file_order):
            file_id = file_info.get('id')
            original_filename = file_info.get('filename')
            
            logger.info(f"Processing file {order_index + 1}: {original_filename} (ID: {file_id})")
            
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
            logger.info(f"Looking for file at: {file_path}")
            
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                # List all files in directory for debugging
                logger.info(f"Files in directory: {os.listdir(temp_dir)}")
                continue
            
            # Read and add each page from the current PDF
            try:
                with open(file_path, 'rb') as pdf_file:
                    pdf_reader = pypdf.PdfReader(pdf_file)
                    page_count = len(pdf_reader.pages)
                    
                    logger.info(f"Adding {page_count} pages from {original_filename}")
                    
                    # Add each page from this PDF to the merger
                    for page_num, page in enumerate(pdf_reader.pages):
                        merger.add_page(page)
                        logger.debug(f"Added page {page_num + 1} from {original_filename}")
                    
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
            output_filename = f"processed_{processed_files[0]['filename'].replace('.pdf', '')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        else:
            output_filename = f"merged_{len(processed_files)}_files_{total_pages}_pages_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        output_path = os.path.join(temp_dir, output_filename)
        
        # Write the merged PDF
        with open(output_path, 'wb') as output_file:
            merger.write(output_file)
        
        # Close the merger
        merger.close()
        
        # Store merged PDF info for download
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
        logger.info(f"Merge ID: {merged_id}")
        
        # Return merge info instead of file
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
    """Download the merged PDF by ID with custom filename support"""
    try:
        if merged_id not in merged_pdfs:
            return jsonify({'error': 'Merged PDF not found or expired'}), 404
        
        merged_info = merged_pdfs[merged_id]
        output_path = merged_info['path']
        original_filename = merged_info['filename']
        
        # Get custom filename from query parameter
        custom_filename = request.args.get('filename')
        
        if custom_filename:
            # Ensure the custom filename has .pdf extension
            if not custom_filename.lower().endswith('.pdf'):
                custom_filename += '.pdf'
            
            # Sanitize the filename
            download_filename = secure_filename(custom_filename)
            
            # If sanitization removed everything, fall back to original
            if not download_filename or download_filename == '.pdf':
                download_filename = original_filename
        else:
            download_filename = original_filename
        
        if not os.path.exists(output_path):
            return jsonify({'error': 'File not found on server'}), 404
        
        logger.info(f"Downloading merged PDF: {download_filename} (Original: {original_filename})")
        
        return send_file(
            output_path,
            as_attachment=True,
            download_name=download_filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Error downloading merged PDF: {str(e)}")
        return jsonify({'error': 'Error downloading file'}), 500

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# Production-ready startup
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

class PDFMergerPro {
    constructor() {
        this.selectedFiles = [];
        this.sessionId = null;
        this.mergedId = null;
        this.currentFilename = '';
        this.maxFiles = 10;
        this.maxFileSize = 50 * 1024 * 1024; // 50MB
        this.sortable = null;
        this.isProcessing = false;
        
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        const fileInput = document.getElementById('fileInput');
        const uploadArea = document.getElementById('uploadArea');
        const uploadBtn = document.getElementById('uploadBtn');
        
        // File input change - SINGLE EVENT LISTENER
        fileInput.addEventListener('change', (e) => {
            if (!this.isProcessing) {
                this.isProcessing = true;
                console.log('File input changed:', e.target.files);
                this.handleFileSelection(e);
            }
        });
        
        // Upload button click - prevent event propagation
        uploadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!this.isProcessing) {
                console.log('Upload button clicked');
                fileInput.click();
            }
        });
        
        // Upload area drag and drop - but NOT click
        uploadArea.addEventListener('dragover', (e) => this.handleDragOver(e));
        uploadArea.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        uploadArea.addEventListener('drop', (e) => this.handleDrop(e));
        
        // Filename input event listeners - Simplified for direct editing
        this.initializeFilenameEditor();
    }
    
    initializeFilenameEditor() {
        const filenameInput = document.getElementById('editableFilename');
        
        if (filenameInput) {
            // Always make it editable - no button needed
            filenameInput.disabled = false;
            
            // Handle Enter key to save and blur
            filenameInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    filenameInput.blur(); // This will trigger the save
                }
            });
            
            // Handle blur to save
            filenameInput.addEventListener('blur', () => {
                this.saveFilename();
            });
            
            // Handle input changes for real-time validation
            filenameInput.addEventListener('input', () => {
                this.validateFilename();
            });
            
            // Handle click to position cursor
            filenameInput.addEventListener('click', () => {
                // Filename is already editable, cursor will position automatically
                console.log('Filename clicked - ready for editing');
            });
            
            // Visual feedback on focus
            filenameInput.addEventListener('focus', () => {
                this.showNotification('Edit filename and press Enter or click elsewhere to save', 'info');
            });
        }
    }
    
    initializeSortable() {
        const container = document.getElementById('pdfPreviewContainer');
        
        if (this.sortable) {
            this.sortable.destroy();
        }
        
        this.sortable = new Sortable(container, {
            animation: 200,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            filter: '.add-more-card',
            onStart: (evt) => {
                document.body.style.userSelect = 'none';
            },
            onEnd: (evt) => {
                document.body.style.userSelect = '';
                this.updateOrderBadges();
            }
        });
    }
    
    handleFileSelection(e) {
        const files = Array.from(e.target.files);
        console.log('Selected files:', files);
        if (files.length > 0) {
            this.processNewFiles(files);
        }
        // Reset the input to allow selecting the same files again
        e.target.value = '';
        this.isProcessing = false;
    }
    
    handleDragOver(e) {
        e.preventDefault();
        document.getElementById('uploadArea').classList.add('drag-over');
    }
    
    handleDragLeave(e) {
        e.preventDefault();
        document.getElementById('uploadArea').classList.remove('drag-over');
    }
    
    handleDrop(e) {
        e.preventDefault();
        document.getElementById('uploadArea').classList.remove('drag-over');
        
        const files = Array.from(e.dataTransfer.files);
        console.log('Dropped files:', files);
        this.processNewFiles(files);
    }
    
    async processNewFiles(files) {
        console.log('Processing files:', files);
        
        // Validate files
        const validFiles = [];
        
        for (let file of files) {
            console.log(`Validating file: ${file.name}, type: ${file.type}, size: ${file.size}`);
            
            if (file.type !== 'application/pdf') {
                this.showNotification('Only PDF files are allowed', 'error');
                continue;
            }
            
            if (file.size > this.maxFileSize) {
                this.showNotification(`File ${file.name} is too large. Maximum size is 50MB`, 'error');
                continue;
            }
            
            if (this.selectedFiles.length >= this.maxFiles) {
                this.showNotification(`Maximum ${this.maxFiles} files allowed in free version`, 'error');
                break;
            }
            
            validFiles.push(file);
        }
        
        if (validFiles.length === 0) {
            console.log('No valid files to process');
            return;
        }
        
        console.log('Valid files:', validFiles);
        
        // Show processing
        this.showProgress('Generating previews...', 20);
        
        try {
            const previews = await this.uploadAndGeneratePreviews(validFiles);
            console.log('Generated previews:', previews);
            
            // Add to existing files
            this.selectedFiles = [...this.selectedFiles, ...previews];
            this.updatePreviewDisplay();
            this.hideProgress();
            
            this.showNotification(`${validFiles.length} file(s) added successfully`, 'success');
        } catch (error) {
            console.error('Error processing files:', error);
            this.hideProgress();
            this.showNotification('Error processing files: ' + error.message, 'error');
        }
    }
    
    async uploadAndGeneratePreviews(files) {
        const formData = new FormData();
        files.forEach(file => {
            console.log(`Adding file to FormData: ${file.name}`);
            formData.append('pdf_files', file);
        });
        
        // If we have an existing session, include it
        if (this.sessionId) {
            formData.append('existing_session', this.sessionId);
        }
        
        console.log('Sending upload request...');
        
        const response = await fetch('/upload-preview', {
            method: 'POST',
            body: formData
        });
        
        console.log('Upload response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Upload error response:', errorText);
            
            try {
                const error = JSON.parse(errorText);
                throw new Error(error.error || 'Failed to process files');
            } catch {
                throw new Error(`Server error: ${response.status}`);
            }
        }
        
        const result = await response.json();
        console.log('Upload result:', result);
        
        if (result.success) {
            this.sessionId = result.session_id;
            return result.previews;
        } else {
            throw new Error('Failed to generate previews');
        }
    }
    
    updatePreviewDisplay() {
        const container = document.getElementById('pdfPreviewContainer');
        const section = document.getElementById('filePreviewSection');
        const uploadArea = document.getElementById('uploadArea');
        const successSection = document.getElementById('successSection');
        
        console.log('Updating preview display, files count:', this.selectedFiles.length);
        
        if (this.selectedFiles.length === 0) {
            section.style.display = 'none';
            uploadArea.style.display = 'block';
            successSection.style.display = 'none';
            return;
        }
        
        // Hide upload area when files are selected, but keep preview section visible
        uploadArea.style.display = 'none';
        section.style.display = 'block';
        // Don't hide success section if it's already shown
        
        // Clear existing content
        container.innerHTML = '';
        
        // Remove existing drag hint
        const existingHint = container.parentElement.querySelector('.drag-hint');
        if (existingHint) {
            existingHint.remove();
        }
        
        // Add drag hint for multiple files
        if (this.selectedFiles.length > 1) {
            const dragHint = document.createElement('div');
            dragHint.className = 'drag-hint';
            dragHint.innerHTML = '<i class="fas fa-info-circle"></i> Drag and drop the cards below to reorder your PDFs';
            container.parentElement.insertBefore(dragHint, container);
        }
        
        // Add preview cards
        this.selectedFiles.forEach((file, index) => {
            const card = this.createPreviewCard(file, index);
            container.appendChild(card);
        });
        
        // Add "Add More" card
        const addMoreCard = this.createAddMoreCard();
        container.appendChild(addMoreCard);
        
        // Initialize sortable after adding cards
        this.initializeSortable();
        this.updateOrderBadges();
        
        // Update merge button text
        this.updateMergeButton();
    }
    
    createPreviewCard(file, index) {
        const card = document.createElement('div');
        card.className = 'pdf-preview-card';
        card.setAttribute('data-file-id', file.id);
        
        // Create thumbnail element
        let thumbnailElement;
        if (file.thumbnail && file.thumbnail !== "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTUwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDE1MCAyNDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxNTAiIGhlaWdodD0iMTgwIiBmaWxsPSIjRjVGNUY1Ii8+CjxwYXRoIGQ9Ik0zMCA0MEgxMjBWMTQwSDMwVjQwWiIgZmlsbD0iI0U1RTVFNSIvPgo8dGV4dCB4PSI3NSIgeT0iMTAwIiBmb250LWZhbWlseT0iQXJpYWwsIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPlBERjwvdGV4dD4KPC9zdmc+") {
            thumbnailElement = `<img src="${file.thumbnail}" alt="PDF Preview" class="pdf-thumbnail" onerror="this.style.display='none'">`;
        } else {
            thumbnailElement = `<div class="pdf-thumbnail pdf-placeholder">
                <i class="fas fa-file-pdf"></i>
                <span>PDF</span>
            </div>`;
        }
        
        card.innerHTML = `
            <div class="pdf-order-badge">${index + 1}</div>
            <button class="pdf-remove-btn" onclick="pdfMerger.removeFile('${file.id}')">
                <i class="fas fa-times"></i>
            </button>
            
            ${thumbnailElement}
            
            <div class="pdf-info">
                <div class="pdf-filename" title="${file.filename}">${this.truncateFilename(file.filename)}</div>
                <div class="pdf-details">
                    <span><i class="fas fa-file-alt"></i> ${file.pages || 0} pages</span>
                    <span><i class="fas fa-weight"></i> ${this.formatFileSize(file.size)}</span>
                </div>
            </div>
        `;
        
        return card;
    }
    
    createAddMoreCard() {
        const card = document.createElement('div');
        card.className = 'add-more-card';
        card.onclick = (e) => {
            e.stopPropagation();
            console.log('Add more card clicked');
            if (!this.isProcessing) {
                document.getElementById('fileInput').click();
            }
        };
        
        card.innerHTML = `
            <i class="fas fa-plus-circle"></i>
            <h4>Add More PDFs</h4>
            <p>Click to select additional files</p>
        `;
        
        return card;
    }
    
    removeFile(fileId) {
        console.log('Removing file:', fileId);
        this.selectedFiles = this.selectedFiles.filter(file => file.id !== fileId);
        this.updatePreviewDisplay();
        
        this.showNotification('File removed', 'success');
    }
    
    clearAllFiles() {
        console.log('Clearing all files');
        this.selectedFiles = [];
        this.sessionId = null;
        this.mergedId = null;
        this.currentFilename = '';
        document.getElementById('fileInput').value = '';
        this.updatePreviewDisplay();
        this.showNotification('All files cleared', 'success');
    }
    
    startNewMerge() {
        console.log('Starting new merge session');
        this.selectedFiles = [];
        this.sessionId = null;
        this.mergedId = null;
        this.currentFilename = '';
        document.getElementById('fileInput').value = '';
        
        // Show upload area and hide success section
        document.getElementById('uploadArea').style.display = 'block';
        document.getElementById('filePreviewSection').style.display = 'none';
        document.getElementById('successSection').style.display = 'none';
        
        // Scroll to top
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
        
        this.showNotification('Ready for new PDFs', 'success');
    }
    
    updateOrderBadges() {
        const cards = document.querySelectorAll('.pdf-preview-card');
        cards.forEach((card, index) => {
            const badge = card.querySelector('.pdf-order-badge');
            if (badge) {
                badge.textContent = index + 1;
            }
        });
    }
    
    updateMergeButton() {
        const mergeBtn = document.getElementById('mergeBtn');
        const fileCount = this.selectedFiles.length;
        
        if (fileCount === 0) {
            mergeBtn.innerHTML = '<i class="fas fa-file-pdf"></i> Select PDF Files';
            mergeBtn.disabled = true;
        } else if (fileCount === 1) {
            mergeBtn.innerHTML = '<i class="fas fa-download"></i> Process PDF';
            mergeBtn.disabled = false;
        } else {
            mergeBtn.innerHTML = `<i class="fas fa-compress-alt"></i> Merge ${fileCount} PDFs`;
            mergeBtn.disabled = false;
        }
    }
    
    async mergePDFs() {
        if (this.selectedFiles.length < 1) {
            this.showNotification('Please select at least 1 PDF file', 'error');
            return;
        }
        
        console.log('Starting merge process...');
        
        // Get current order from DOM
        const cards = Array.from(document.querySelectorAll('.pdf-preview-card'));
        const orderedFiles = cards.map(card => {
            const fileId = card.getAttribute('data-file-id');
            const file = this.selectedFiles.find(file => file.id === fileId);
            if (file) {
                return {
                    id: file.id,
                    filename: file.filename,
                    file_index: file.file_index,
                    file_path: file.file_path
                };
            }
            return null;
        }).filter(file => file !== null);
        
        console.log('Ordered files for merge:', orderedFiles);
        
        this.showProgress('Preparing merge...', 10);
        
        try {
            const response = await fetch('/merge-ordered', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    file_order: orderedFiles
                })
            });
            
            console.log('Merge response status:', response.status);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('Merge error response:', errorText);
                
                try {
                    const error = JSON.parse(errorText);
                    throw new Error(error.error || 'Failed to merge PDFs');
                } catch {
                    throw new Error(`Server error: ${response.status}`);
                }
            }
            
            this.showProgress('Processing complete...', 90);
            
            const result = await response.json();
            console.log('Merge result:', result);
            
            if (result.success) {
                this.mergedId = result.merged_id;
                this.currentFilename = result.filename.replace('.pdf', ''); // Store without extension
                
                this.showProgress('Complete!', 100);
                
                // Show success section but keep preview section visible
                this.showSuccessSection(result);
                
                this.showNotification('PDFs processed successfully!', 'success');
                
                // Hide progress after showing success
                setTimeout(() => {
                    this.hideProgress();
                }, 300);
                
                // Auto-scroll to success section after a short delay
                setTimeout(() => {
                    this.scrollToSuccessSection();
                }, 400);
                
            } else {
                throw new Error('Merge failed');
            }
            
        } catch (error) {
            console.error('Merge error:', error);
            this.hideProgress();
            this.showNotification(error.message, 'error');
        }
    }
    
    scrollToSuccessSection() {
        const successSection = document.getElementById('successSection');
        if (successSection && successSection.style.display !== 'none') {
            const elementPosition = successSection.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - 100; // 100px offset from top
            
            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
            
            console.log('Auto-scrolled to success section');
            
            // Add a subtle highlight effect to draw attention
            successSection.classList.add('highlight-section');
            setTimeout(() => {
                successSection.classList.remove('highlight-section');
            }, 3000);
        }
    }
    
    showSuccessSection(result) {
        const successSection = document.getElementById('successSection');
        const successMessage = document.getElementById('successMessage');
        const mergeSummary = document.getElementById('mergeSummary');
        const filenameInput = document.getElementById('editableFilename');
        
        // Update success message
        if (result.file_count === 1) {
            successMessage.textContent = `Your PDF has been processed successfully`;
        } else {
            successMessage.textContent = `${result.file_count} PDFs have been merged successfully`;
        }
        
        // Set the filename in the input field - Always editable now
        filenameInput.value = this.currentFilename;
        filenameInput.disabled = false; // Always enabled for direct editing
        
        // Update summary
        mergeSummary.innerHTML = `
            <div class="summary-item">
                <i class="fas fa-file-pdf"></i>
                <span>Files processed: <strong>${result.file_count}</strong></span>
            </div>
            <div class="summary-item">
                <i class="fas fa-file-alt"></i>
                <span>Total pages: <strong>${result.total_pages}</strong></span>
            </div>
            <div class="summary-item">
                <i class="fas fa-file"></i>
                <span>Original name: <strong>${result.filename}</strong></span>
            </div>
        `;
        
        // Show success section (keep preview section visible)
        successSection.style.display = 'block';
    }
    
    saveFilename() {
        const filenameInput = document.getElementById('editableFilename');
        
        let newFilename = filenameInput.value.trim();
        
        // Validate filename
        if (!newFilename) {
            newFilename = this.currentFilename; // Revert to original
            filenameInput.value = newFilename;
            this.showNotification('Filename cannot be empty - reverted to original', 'warning');
        } else {
            // Remove invalid characters
            const sanitized = newFilename.replace(/[<>:"/\\|?*]/g, '');
            if (sanitized !== newFilename) {
                filenameInput.value = sanitized;
                this.showNotification('Invalid characters removed from filename', 'warning');
            }
            this.currentFilename = sanitized;
            this.showNotification('Filename updated successfully', 'success');
        }
    }
    
    validateFilename() {
        const filenameInput = document.getElementById('editableFilename');
        const value = filenameInput.value;
        
        // Remove invalid characters in real-time
        const sanitized = value.replace(/[<>:"/\\|?*]/g, '');
        if (sanitized !== value) {
            filenameInput.value = sanitized;
        }
    }
    
    downloadMergedPDF() {
        if (!this.mergedId) {
            this.showNotification('No merged PDF available for download', 'error');
            return;
        }
        
        // Get the current filename from input (in case user edited it)
        const filenameInput = document.getElementById('editableFilename');
        const currentFilename = filenameInput.value.trim() || this.currentFilename;
        
        console.log('Downloading merged PDF with ID:', this.mergedId);
        console.log('Using custom filename:', currentFilename);
        
        // Create download URL with custom filename
        let downloadUrl = `/download-merged/${this.mergedId}`;
        
        // Add custom filename as query parameter if available
        if (currentFilename) {
            const encodedFilename = encodeURIComponent(currentFilename);
            downloadUrl += `?filename=${encodedFilename}`;
        }
        
        console.log('Download URL:', downloadUrl);
        
        // Create hidden link and trigger download
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        this.showNotification('Download started with custom filename', 'success');
    }
    
    // Utility methods
    truncateFilename(filename, maxLength = 20) {
        if (filename.length <= maxLength) return filename;
        const ext = filename.split('.').pop();
        const name = filename.substring(0, filename.lastIndexOf('.'));
        const truncated = name.substring(0, maxLength - ext.length - 4) + '...';
        return truncated + '.' + ext;
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }
    
    showProgress(message, percentage) {
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        progressBar.style.display = 'block';
        progressFill.style.width = percentage + '%';
        progressText.textContent = message;
    }
    
    hideProgress() {
        const progressBar = document.getElementById('progressBar');
        progressBar.style.display = 'none';
    }
    
    showNotification(message, type) {
        console.log(`Notification: ${type} - ${message}`);
        
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i>
            <span>${message}</span>
        `;
        
        document.body.appendChild(notification);
        setTimeout(() => notification.classList.add('show'), 100);
        
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (document.body.contains(notification)) {
                    document.body.removeChild(notification);
                }
            }, 300);
        }, 4000);
    }
}

// Initialize the PDF Merger when page loads
let pdfMerger;
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Content Loaded - Initializing PDF Merger');
    pdfMerger = new PDFMergerPro();
});

// Make functions globally accessible
function mergePDFs() {
    if (pdfMerger) {
        pdfMerger.mergePDFs();
    } else {
        console.error('PDF Merger not initialized');
    }
}

function clearAllFiles() {
    if (pdfMerger) {
        pdfMerger.clearAllFiles();
    } else {
        console.error('PDF Merger not initialized');
    }
}

function downloadMergedPDF() {
    if (pdfMerger) {
        pdfMerger.downloadMergedPDF();
    } else {
        console.error('PDF Merger not initialized');
    }
}

function startNewMerge() {
    if (pdfMerger) {
        pdfMerger.startNewMerge();
    } else {
        console.error('PDF Merger not initialized');
    }
}

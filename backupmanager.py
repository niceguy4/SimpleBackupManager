import os
import zipfile
import threading
import time
import json
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, redirect
import shutil
import schedule
import requests
import logging
import traceback


logging.basicConfig(
    filename='backup_manager.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

CONFIG_FILE = 'backup_config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            if 'stats' not in data:
                data['stats'] = {'run_count': 0, 'last_backup': 'Never', 'next_backup': 'Not scheduled'}
            if 'webhook_url' not in data:
                data['webhook_url'] = ''
            if 'scheduler_enabled' not in data:
                data['scheduler_enabled'] = True
            if 'retention_count' not in data:
                data['retention_count'] = 0  # 0 means keep all backups
            if 'ui_state' not in data:
                data['ui_state'] = {
                    'history_collapsed': 'false',
                    'entries_collapsed': 'false',
                    'destination_collapsed': 'false',
                    'stats_collapsed': 'false'
                }
            return data
    return {
        'folders': [],
        'files': [],
        'zip_name': 'backup',
        'frequency_minutes': 60,
        'destination': os.getcwd(),
        'webhook_url': '',
        'scheduler_enabled': True,
        'retention_count': 0,  # 0 means keep all backups
        'history': [],
        'stats': {
            'run_count': 0,
            'last_backup': 'Never',
            'next_backup': 'Not scheduled'
        },
        'ui_state': {
            'history_collapsed': 'false',
            'entries_collapsed': 'false',
            'destination_collapsed': 'false',
            'stats_collapsed': 'false'
        }
    }


def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(backup_config, f, indent=2)

# update the next backup time
def update_next_backup_time():
    if backup_config.get('scheduler_enabled', True):
        now = datetime.now()
        next_run = now + timedelta(minutes=backup_config['frequency_minutes'])
        backup_config['stats']['next_backup'] = next_run.strftime('%Y-%m-%d %H:%M:%S')
    else:
        backup_config['stats']['next_backup'] = 'Scheduler disabled'
    save_config()

backup_config = load_config()

html_template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Backup Manager</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #121212;
            color: #f0f0f0;
            padding: 40px;
            line-height: 1.6;
        }
        h1, h2, h3 {
            color: #00bcd4;
        }
        .section-header {
            cursor: pointer;
            display: flex;
            align-items: center;
            user-select: none;
        }
        .section-header i {
            margin-right: 10px;
            transition: transform 0.3s ease;
        }
        .section-header.collapsed i {
            transform: rotate(-90deg);
        }
        .section-content {
            overflow: hidden;
            transition: max-height 0.3s ease;
            max-height: 2000px; /* A large value to accommodate content */
        }
        .section-content.collapsed {
            max-height: 0;
        }
        label {
            font-weight: bold;
            margin-top: 10px;
        }
        input, select, textarea {
            padding: 10px;
            border-radius: 8px;
            border: 1px solid #444;
            background-color: #1e1e2f;
            color: white;
            margin-bottom: 10px;
            width: 100%;
        }
        button {
            background: linear-gradient(135deg, #7c4dff, #6200ea);
            color: white;
            padding: 14px 24px;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            margin-top: 10px;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
        }
        button:hover {
            background: linear-gradient(135deg, #9575cd, #5e35b1);
            transform: translateY(-2px);
            box-shadow: 0 6px 14px rgba(0, 0, 0, 0.4);
        }
        .section {
            margin-bottom: 30px;
            background-color: #1e1e2f;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.5);
        }
        .backup-entry {
            background-color: #2a2a40;
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 5px;
        }
        ul {
            list-style-type: none;
            padding-left: 0;
        }
        li {
            background-color: #2a2a40;
            margin-bottom: 4px;
            padding: 8px;
            border-radius: 6px;
        }
    </style>
</head>

<body>
<nav style="display: flex; gap: 20px; justify-content: center; margin-bottom: 30px;">
    <a href="#settings" style="text-decoration: none; color: #00bcd4; font-weight: bold;"><i class="fas fa-cog"></i> Settings</a>
    <a href="#entries" style="text-decoration: none; color: #00bcd4; font-weight: bold;"><i class="fas fa-folder-open"></i> Backup Entries</a>
    <a href="#history" style="text-decoration: none; color: #00bcd4; font-weight: bold;"><i class="fas fa-history"></i> History</a>
    <a href="#stats" style="text-decoration: none; color: #00bcd4; font-weight: bold;"><i class="fas fa-chart-bar"></i> Stats</a>
    <a href="#destination" style="text-decoration: none; color: #00bcd4; font-weight: bold;"><i class="fas fa-download"></i> Destination Folder</a>
</nav>

<h1 id="settings" style="text-align: center; font-size: 2.5rem; margin-bottom: 20px;">Backup Manager</h1>

<form method="POST">
<!-- Hidden inputs to store the collapsed state -->
<input type="hidden" id="history_collapsed" name="history_collapsed" value="{{ config.get('ui_state', {}).get('history_collapsed', 'false') }}">
<input type="hidden" id="entries_collapsed" name="entries_collapsed" value="{{ config.get('ui_state', {}).get('entries_collapsed', 'false') }}">
<input type="hidden" id="destination_collapsed" name="destination_collapsed" value="{{ config.get('ui_state', {}).get('destination_collapsed', 'false') }}">
<input type="hidden" id="stats_collapsed" name="stats_collapsed" value="{{ config.get('ui_state', {}).get('stats_collapsed', 'false') }}">

<div class="section">
    <label>Zip File Base Name:</label>
    <input name="zip_name" required value="{{ config['zip_name'] }}">

    <label>Backup Frequency (minutes):</label>
    <input type="number" name="frequency_minutes" required value="{{ config['frequency_minutes'] }}">

    <label>Destination Folder:</label>
    <input name="destination" required value="{{ config['destination'] }}">

    <label>Discord Webhook URL:</label>
    <input name="webhook_url" value="{{ config['webhook_url'] }}">

    <label>Number of Backups to Keep (0 = keep all):</label>
    <input type="number" name="retention_count" min="0" value="{{ config['retention_count'] }}">

</div>

<div class="section">
    <label>Files to Backup (format: path | label):</label>
    <textarea name="files" rows="5">{% for f in config['files'] %}{{ f['path'] }} | {{ f['label'] }}
{% endfor %}</textarea>

    <label>Folders to Backup (format: path | label):</label>
    <textarea name="folders" rows="5">{% for f in config['folders'] %}{{ f['path'] }} | {{ f['label'] }}
{% endfor %}</textarea>
</div>

<div style="display: flex; justify-content: center; gap: 20px; margin-bottom: 40px;">
    <button type="submit"><i class="fas fa-save"></i> Save Settings</button>
</form>
<form action="/run_backup" method="POST">
    <button type="submit"><i class="fas fa-play"></i> Run Backup Now</button>
</form>
<form action="/clear_history" method="POST">
    <button type="submit"><i class="fas fa-trash"></i> Clear History</button>
</form>
<form action="/toggle_scheduler" method="POST">
    <button type="submit">{{ '🟢 Enabled - Click to Stop' if config['scheduler_enabled'] else '🔴 Stopped - Click to Start' }}</button>
</form>
</div>

{% if backup_warnings %}
<hr style="margin: 40px 0; border: 0; border-top: 1px solid #b71c1c;">
<h2 style="color: #f44336;"><i class="fas fa-exclamation-triangle"></i> Backup Warnings</h2>
<ul>
  {% for warning in backup_warnings %}
  <li style="color: #ffcdd2; background: #2f1e1e;">{{ warning }}</li>
  {% endfor %}
</ul>
{% endif %}

<!-- Collapsible History Section -->
<div class="section">
    <h2 id="history" class="section-header {{ 'collapsed' if config.get('ui_state', {}).get('history_collapsed', 'false') == 'true' else '' }}">
        <i class="fas fa-chevron-down"></i> Backup History
    </h2>
    <div class="section-content {{ 'collapsed' if config.get('ui_state', {}).get('history_collapsed', 'false') == 'true' else '' }}">
        {% for entry in config['history'] %}
        <div class="backup-entry">
            {{ entry }}
        </div>
        {% endfor %}
    </div>
</div>

<!-- Collapsible Backup Entries Section -->
<div class="section">
    <h2 id="entries" class="section-header {{ 'collapsed' if config.get('ui_state', {}).get('entries_collapsed', 'false') == 'true' else '' }}">
        <i class="fas fa-chevron-down"></i> Current Backup Entries
    </h2>
    <div class="section-content {{ 'collapsed' if config.get('ui_state', {}).get('entries_collapsed', 'false') == 'true' else '' }}">
        <h3>Folders</h3>
        <ul>
        {% for folder in config['folders'] %}
            <li>{{ folder['label'] }} ({{ folder['path'] }})</li>
        {% endfor %}
        </ul>
        <h3>Files</h3>
        <ul>
        {% for file in config['files'] %}
            <li>{{ file['label'] }} ({{ file['path'] }})</li>
        {% endfor %}
        </ul>
    </div>
</div>

<!-- Collapsible Destination Folder Section -->
<div class="section">
    <h2 id="destination" class="section-header {{ 'collapsed' if config.get('ui_state', {}).get('destination_collapsed', 'false') == 'true' else '' }}">
        <i class="fas fa-chevron-down"></i> Contents of Destination Folder
    </h2>
    <div class="section-content {{ 'collapsed' if config.get('ui_state', {}).get('destination_collapsed', 'false') == 'true' else '' }}">
        <ul>
        {% for file in destination_files %}
            <li>{{ file }}</li>
        {% endfor %}
        </ul>
    </div>
</div>

<!-- Collapsible Stats Section -->
<div class="section">
    <h2 id="stats" class="section-header {{ 'collapsed' if config.get('ui_state', {}).get('stats_collapsed', 'false') == 'true' else '' }}">
        <i class="fas fa-chevron-down"></i> Backup Stats
    </h2>
    <div class="section-content {{ 'collapsed' if config.get('ui_state', {}).get('stats_collapsed', 'false') == 'true' else '' }}">
        <ul>
            <li>Total files to backup: {{ stats['file_count'] }}</li>
            <li>Total folders to backup: {{ stats['folder_count'] }}</li>
            <li>Total size to backup: {{ stats['total_size'] }} MB</li>
            <li>Total backups run: {{ config['stats']['run_count'] }}</li>
            <li>Last backup: {{ config['stats']['last_backup'] }}</li>
            <li>Next backup: {{ config['stats']['next_backup'] }}</li>
        </ul>
    </div>
</div>

<script>
// JavaScript to handle collapsible sections
document.addEventListener('DOMContentLoaded', function() {
    // Get all section headers
    const sectionHeaders = document.querySelectorAll('.section-header');
    
    // Add click event listeners to each header
    sectionHeaders.forEach(header => {
        header.addEventListener('click', function() {
            // Toggle the collapsed class on the header
            this.classList.toggle('collapsed');
            
            // Toggle the collapsed class on the next sibling (the content)
            const content = this.nextElementSibling;
            content.classList.toggle('collapsed');
            
            // Update the hidden input value
            const sectionId = this.id;
            const hiddenInput = document.getElementById(sectionId + '_collapsed');
            if (hiddenInput) {
                hiddenInput.value = this.classList.contains('collapsed') ? 'true' : 'false';
            }
        });
    });
});
</script>
</body>
</html>
'''

def run_backup():

    # Check permissions before starting backup
    paths_to_check = {
        'destination': backup_config['destination'],
        'files': backup_config['files'],
        'folders': backup_config['folders']
    }
    
    permission_warnings = check_filesystem_permissions(paths_to_check)
    if permission_warnings:
        for warning in permission_warnings:
            logging.warning(warning)
        
        # Add permission warnings to the backup warnings
        backup_config['last_warnings'] = permission_warnings
        save_config()
        
        # Return failure if serious permission issues
        if any("No write permission for destination" in w for w in permission_warnings):
            return False, permission_warnings

    webhook_url = backup_config.get("webhook_url")
    date_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    zip_filename = f"{backup_config['zip_name']}_{date_str}.zip"
    zip_path = os.path.join(backup_config['destination'], zip_filename)

    warnings = []
    success = True
    backup_size = 0
    files_processed = 0
    
    logging.info(f"Starting backup: {zip_filename}")
    
    # Check if destination folder exists
    if not os.path.exists(backup_config['destination']):
        try:
            os.makedirs(backup_config['destination'])
            logging.info(f"Created destination directory: {backup_config['destination']}")
        except Exception as e:
            error_msg = f"Failed to create destination directory: {str(e)}"
            warnings.append(error_msg)
            logging.error(f"{error_msg}\n{traceback.format_exc()}")
            success = False

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Process folders
            for folder in backup_config['folders']:
                path = folder['path']
                if os.path.exists(path):
                    try:
                        for root, _, files in os.walk(path):
                            for file in files:
                                try:
                                    full_path = os.path.join(root, file)
                                    arcname = os.path.relpath(full_path, path)
                                    zipf.write(full_path, os.path.join(os.path.basename(path), arcname))
                                    files_processed += 1
                                except Exception as e:
                                    error_msg = f"Error adding file {full_path} to zip: {str(e)}"
                                    warnings.append(error_msg)
                                    logging.warning(error_msg)
                    except Exception as e:
                        error_msg = f"Error processing folder {path}: {str(e)}"
                        warnings.append(error_msg)
                        logging.error(f"{error_msg}\n{traceback.format_exc()}")
                else:
                    error_msg = f"Missing folder: {path}"
                    warnings.append(error_msg)
                    logging.warning(error_msg)

            # Process files
            for file in backup_config['files']:
                path = file['path']
                if os.path.exists(path):
                    try:
                        zipf.write(path, os.path.basename(path))
                        files_processed += 1
                    except Exception as e:
                        error_msg = f"Error adding file {path} to zip: {str(e)}"
                        warnings.append(error_msg)
                        logging.warning(error_msg)
                else:
                    error_msg = f"Missing file: {path}"
                    warnings.append(error_msg)
                    logging.warning(error_msg)
    except Exception as e:
        error_msg = f"Failed to create zip file: {str(e)}"
        warnings.append(error_msg)
        logging.error(f"{error_msg}\n{traceback.format_exc()}")
        success = False

    # Check if the zip file was created and get its size
    if success and os.path.exists(zip_path):
        try:
            backup_size = os.path.getsize(zip_path) / (1024 * 1024)
            history_entry = f"{zip_filename} - {backup_size:.2f} MB - {files_processed} files"
            logging.info(f"Backup completed: {history_entry}")
        except Exception as e:
            history_entry = f"{zip_filename} - SIZE UNKNOWN - Error: {str(e)}"
            logging.error(f"Error getting backup size: {str(e)}")
    else:
        history_entry = f"{zip_filename} - FAILED"
        logging.error(f"Backup failed: {zip_filename}")
        success = False

    # Update backup history and stats
    backup_config['history'].insert(0, history_entry)
    if len(backup_config['history']) > 20:
        backup_config['history'].pop()
    backup_config['stats']['run_count'] += 1
    backup_config['stats']['last_backup'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    backup_config['last_warnings'] = warnings

    update_next_backup_time()

    # Prepare Discord notification
    status = "✅ Backup completed successfully" if success else "❌ Backup failed"
    if warnings and success:
        status = "⚠️ Backup completed with warnings"
    
    payload = {
        "content": f"**{status}**\nFile: `{zip_filename}`\nTime: {backup_config['stats']['last_backup']}\nWarnings: {len(warnings)}\nSize: {backup_size:.2f} MB" if success else f"**{status}**\nFile: `{zip_filename}`\nTime: {backup_config['stats']['last_backup']}\nWarnings: {len(warnings)}"
    }

    # Send Discord notification if configured
    if webhook_url:
        try:
            response = requests.post(webhook_url, json=payload)
            if response.status_code != 200:
                logging.warning(f"Discord webhook returned non-200 status: {response.status_code}")
        except Exception as e:
            error_msg = f"Failed to send Discord notification: {str(e)}"
            logging.error(f"{error_msg}\n{traceback.format_exc()}")

    save_config()

    # Apply retention policy only if backup was successful
    if success:
        try:
            apply_retention_policy()
        except Exception as e:
            error_msg = f"Error applying retention policy: {str(e)}"
            logging.error(f"{error_msg}\n{traceback.format_exc()}")
    
    return success, warnings

def schedule_backups():
    schedule.every(backup_config['frequency_minutes']).minutes.do(run_backup)
    while True:
        if backup_config.get('scheduler_enabled', True):
            schedule.run_pending()
        time.sleep(1)

def get_stats():
    total_size = 0
    file_count = len(backup_config['files'])
    folder_count = len(backup_config['folders'])

    for file_entry in backup_config['files']:
        path = file_entry['path']
        if os.path.exists(path):
            total_size += os.path.getsize(path)

    for folder_entry in backup_config['folders']:
        path = folder_entry['path']
        if os.path.exists(path):
            for root, _, files in os.walk(path):
                for file in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, file))
                    except:
                        continue

    return {
        'total_size': round(total_size / (1024 * 1024), 2),
        'file_count': file_count,
        'folder_count': folder_count
    }

def validate_path(path):
    """Validate a file or folder path to prevent path traversal attacks"""
    # Normalize the path to handle different formats
    norm_path = os.path.normpath(path)
    
    # Check for path traversal attempts
    if '..' in norm_path.split(os.sep):
        return False, "Path contains illegal traversal patterns"
    
    # Check for absolute path (reasonable security check)
    if not os.path.isabs(norm_path):
        return False, "Only absolute paths are allowed"
        
    # Check for suspicious patterns
    suspicious_patterns = ['~', '$', '|', ';', '>', '<', '&']
    if any(pattern in path for pattern in suspicious_patterns):
        return False, "Path contains suspicious characters"
    
    return True, "Path is valid"

def check_filesystem_permissions(paths_to_check):
    """
    Check if the application has necessary permissions for all files and folders
    Returns a list of warnings for any permission issues
    """
    warnings = []
    
    # Check destination folder
    dest_dir = paths_to_check.get('destination', '')
    if dest_dir:
        if os.path.exists(dest_dir):
            if not os.access(dest_dir, os.W_OK):
                warnings.append(f"No write permission for destination folder: {dest_dir}")
        else:
            # Check if parent directory is writable to create the destination
            parent_dir = os.path.dirname(dest_dir)
            if not os.access(parent_dir, os.W_OK):
                warnings.append(f"Cannot create destination folder: no write permission for {parent_dir}")
    
    # Check source files
    for file_entry in paths_to_check.get('files', []):
        path = file_entry.get('path', '')
        if path and os.path.exists(path):
            if not os.access(path, os.R_OK):
                warnings.append(f"No read permission for file: {path}")
    
    # Check source folders
    for folder_entry in paths_to_check.get('folders', []):
        path = folder_entry.get('path', '')
        if path and os.path.exists(path):
            if not os.access(path, os.R_OK):
                warnings.append(f"No read permission for folder: {path}")
            
            # Check if we can traverse the directory
            if not os.access(path, os.X_OK):
                warnings.append(f"No traverse permission for folder: {path}")
                
            # Check sample of subfolders for read permissions
            for root, dirs, files in os.walk(path, topdown=True, onerror=lambda err: warnings.append(f"Error accessing subfolder in {path}: {str(err)}")):
                # Limit depth for performance
                if root.count(os.sep) - path.count(os.sep) > 2:
                    del dirs[:]
                    continue
                    
                # Check a few files in each directory
                for i, file in enumerate(files):
                    if i >= 3:  # Just check a few files per directory
                        break
                    file_path = os.path.join(root, file)
                    if not os.access(file_path, os.R_OK):
                        warnings.append(f"No read permission for file in subfolder: {file_path}")
                        break  # Just report one file per directory
                
                # Exit early if we've found several issues
                if len(warnings) > 10:
                    warnings.append("Multiple permission issues found. Showing first 10 only.")
                    break
            
    return warnings

def apply_retention_policy():
    """Delete older backups keeping only the most recent ones as specified"""
    retention_count = backup_config.get('retention_count', 0)
    
    # If retention count is 0 or negative, keep all backups
    if retention_count <= 0:
        return
        
    try:
        destination = backup_config['destination']
        zip_prefix = backup_config['zip_name'] + '_'
        
        # Safety check: ensure destination is a directory
        if not os.path.isdir(destination):
            logging.warning(f"Retention policy skipped: destination is not a valid directory: {destination}")
            return
            
        # Get all backup files matching our naming pattern
        backup_files = []
        for filename in os.listdir(destination):
            filepath = os.path.join(destination, filename)
            # Only process files (not directories) that start with our prefix and end with .zip
            if (os.path.isfile(filepath) and 
                filename.startswith(zip_prefix) and 
                filename.endswith('.zip')):
                try:
                    # Store with creation time for sorting
                    file_time = os.path.getctime(filepath)
                    backup_files.append((filepath, filename, file_time))
                except Exception as e:
                    logging.warning(f"Error getting file creation time for {filepath}: {str(e)}")
        
        # Sort by creation time (newest first)
        backup_files.sort(key=lambda x: x[2], reverse=True)
        
        # Keep the most recent N files as specified by retention_count
        files_to_delete = backup_files[retention_count:]
        
        # Log retention policy summary
        logging.info(f"Retention policy: keeping {retention_count} of {len(backup_files)} backups")
        
        # Delete older files and log the actions
        for filepath, filename, _ in files_to_delete:
            # Final safety check - make sure it's a zip file with our expected prefix
            if filename.startswith(zip_prefix) and filename.endswith('.zip'):
                try:
                    os.remove(filepath)
                    message = f"Retention policy: Deleted {filename}"
                    backup_config['history'].insert(0, message)
                    logging.info(message)
                except Exception as e:
                    error_msg = f"Retention policy: Failed to delete {filename}: {str(e)}"
                    backup_config['history'].insert(0, error_msg)
                    logging.error(error_msg)
        
        save_config()
            
    except Exception as e:
        error_msg = f"Failed to apply retention policy: {str(e)}"
        logging.error(f"{error_msg}\n{traceback.format_exc()}")
        backup_config['history'].insert(0, error_msg)

@app.route('/toggle_scheduler', methods=['POST'])
def toggle_scheduler():
    backup_config['scheduler_enabled'] = not backup_config['scheduler_enabled']
    update_next_backup_time()
    save_config()
    return redirect('/')

@app.route('/clear_history', methods=['POST'])
def clear_history():
    backup_config['history'] = []
    save_config()
    return redirect('/')

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':

        dest_path = request.form['destination']
        is_valid, message = validate_path(dest_path)
        if not is_valid:
            # Return error - you could flash a message or return directly
            return render_template_string(html_template, 
                                         config=backup_config, 
                                         destination_files=[], 
                                         stats=get_stats(), 
                                         backup_warnings=[f"Invalid destination path: {message}"])
                                         
        backup_config['destination'] = dest_path
        backup_config['zip_name'] = request.form['zip_name']
        backup_config['frequency_minutes'] = int(request.form['frequency_minutes'])
        backup_config['destination'] = request.form['destination']
        backup_config['webhook_url'] = request.form.get('webhook_url', '').strip()
        backup_config['retention_count'] = int(request.form.get('retention_count', 0))

        backup_config['ui_state'] = {
            'history_collapsed': request.form.get('history_collapsed', 'false'),
            'entries_collapsed': request.form.get('entries_collapsed', 'false'),
            'destination_collapsed': request.form.get('destination_collapsed', 'false'),
            'stats_collapsed': request.form.get('stats_collapsed', 'false')
        }

        files_input = request.form['files'].split('\n')
        backup_config['files'] = []
        for line in files_input:
            if not line.strip():
                continue
                
            parts = line.strip().split('|')
            if len(parts) == 2:
                path = parts[0].strip()
                is_valid, message = validate_path(path)
                if is_valid:
                    backup_config['files'].append({'path': path, 'label': parts[1].strip()})
                else:
                    return render_template_string(html_template, 
                                               config=backup_config, 
                                               destination_files=[], 
                                               stats=get_stats(), 
                                               backup_warnings=[f"Invalid file path '{path}': {message}"])

        folders_input = request.form['folders'].split('\n')
        backup_config['folders'] = []
        for line in folders_input:
            if not line.strip():
                continue
                
            parts = line.strip().split('|')
            if len(parts) == 2:
                path = parts[0].strip()
                is_valid, message = validate_path(path)
                if is_valid:
                    backup_config['folders'].append({'path': path, 'label': parts[1].strip()})
                else:
                    return render_template_string(html_template, 
                                            config=backup_config, 
                                            destination_files=[], 
                                            stats=get_stats(), 
                                            backup_warnings=[f"Invalid folder path '{path}': {message}"])

        save_config()
        schedule.clear()
        schedule.every(backup_config['frequency_minutes']).minutes.do(run_backup)
        update_next_backup_time()

        if 'update_next_backup_time' in globals():
            update_next_backup_time()
            
        return redirect('/')

    try:
        destination_files = os.listdir(backup_config['destination'])
    except Exception:
        destination_files = []

    stats = get_stats()
    return render_template_string(html_template, config=backup_config, destination_files=destination_files, stats=stats, backup_warnings=backup_config.get('last_warnings', []))

@app.route('/run_backup', methods=['POST'])
def manual_backup():
    success, warnings = run_backup()
    return redirect('/')

threading.Thread(target=schedule_backups, daemon=True).start()

if __name__ == '__main__':
    update_next_backup_time()
    app.run(host='0.0.0.0', port=5454)

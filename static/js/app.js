document.addEventListener('DOMContentLoaded', () => {
    // --- Elements ---
    const btnScan = document.getElementById('btn-scan');
    const btnGenerate = document.getElementById('btn-generate');
    const folderPathInput = document.getElementById('folder-path');
    const outputDirInput = document.getElementById('output-dir');
    
    // Config elements
    const cfgWidth = document.getElementById('cfg-width');
    const cfgHeight = document.getElementById('cfg-height');
    const cfgDynamicRange = document.getElementById('cfg-dynamic-range');
    const cfgGap = document.getElementById('cfg-gap');
    const cfgDirection = document.getElementById('cfg-direction');
    const cfgLabels = document.getElementById('cfg-labels');
    const cfgStitch = document.getElementById('cfg-stitch');
    const cfgUploadHost = document.getElementById('cfg-upload-host');
    const groupImgbbKey = document.getElementById('group-imgbb-key');
    const cfgImgbbKey = document.getElementById('cfg-imgbb-key');
    const cfgAutoUpload = document.getElementById('cfg-auto-upload');
    const cfgRememberKey = document.getElementById('cfg-remember-key');
    const btnToggleKey = document.getElementById('btn-toggle-key');
    const btnBrowse = document.getElementById('btn-browse');
    const btnTorrentModal = document.getElementById('btn-torrent-modal');

    // Scan results elements
    const scanResultsDiv = document.getElementById('scan-results');
    const scanSummaryDiv = document.getElementById('scan-summary');
    const albumTreeDiv = document.getElementById('album-tree');

    // Tracklist elements
    const tracklistSection = document.getElementById('tracklist-section');
    const tracklistContent = document.getElementById('tracklist-content');
    const btnCopyTracklist = document.getElementById('btn-copy-tracklist');

    // Progress elements
    const progressSection = document.getElementById('progress-section');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const progressDetail = document.getElementById('progress-detail');
    const progressLog = document.getElementById('progress-log');

    // Gallery elements
    const gallery = document.getElementById('gallery');
    
    // Upload results elements
    const uploadResultsDiv = document.getElementById('upload-results');
    const uploadLinksDiv = document.getElementById('upload-links');
    const btnCopyAllLinks = document.getElementById('btn-copy-all-links');
    
    // Lightbox
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');

    // Toast container
    const toastContainer = document.getElementById('toast-container');

    let currentEventSource = null;
    let currentTracklistData = null; // 存储 tracklist 数据
    let currentUploadResults = [];   // 存储上传结果
    let selectedTracklistFormat = 'plain';
    let selectedLinkFormat = 'direct';

    // --- Init: 恢复保存的 API Key ---
    const savedKey = localStorage.getItem('imgbb_api_key');
    if (savedKey) {
        cfgImgbbKey.value = savedKey;
    }
    const savedAutoUpload = localStorage.getItem('auto_upload');
    if (savedAutoUpload === 'true') {
        cfgAutoUpload.checked = true;
    }

    // --- Utility Functions ---
    const showToast = (message, type = 'info') => {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    };

    const copyToClipboard = async (text, successMsg = '已复制到剪贴板') => {
        try {
            await navigator.clipboard.writeText(text);
            showToast(successMsg, 'success');
            return true;
        } catch (e) {
            // Fallback
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            showToast(successMsg, 'success');
            return true;
        }
    };

    const addLog = (msg, type = 'info') => {
        const p = document.createElement('p');
        p.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
        if (type !== 'info') {
            p.classList.add(type);
        }
        progressLog.appendChild(p);
        progressLog.scrollTop = progressLog.scrollHeight;
    };

    const resetProgress = () => {
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
        progressDetail.textContent = '准备就绪...';
        progressLog.innerHTML = '';
        progressSection.classList.remove('hidden');
    };

    const updateProgress = (processed, total, detailText) => {
        const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
        progressFill.style.width = `${percent}%`;
        progressText.textContent = `${percent}%`;
        if (detailText) {
            progressDetail.textContent = detailText;
        }
    };

    // --- API Key Toggle ---
    btnToggleKey.addEventListener('click', () => {
        const isPassword = cfgImgbbKey.type === 'password';
        cfgImgbbKey.type = isPassword ? 'text' : 'password';
        btnToggleKey.title = isPassword ? '隐藏' : '显示';
    });

    // Save API key preference
    cfgImgbbKey.addEventListener('change', () => {
        if (cfgRememberKey.checked && cfgImgbbKey.value.trim()) {
            localStorage.setItem('imgbb_api_key', cfgImgbbKey.value.trim());
        }
    });

    cfgAutoUpload.addEventListener('change', () => {
        localStorage.setItem('auto_upload', cfgAutoUpload.checked);
    });

    cfgRememberKey.addEventListener('change', () => {
        if (!cfgRememberKey.checked) {
            localStorage.removeItem('imgbb_api_key');
        } else if (cfgImgbbKey.value.trim()) {
            localStorage.setItem('imgbb_api_key', cfgImgbbKey.value.trim());
        }
    });

    // --- Host Toggle ---
    const updateHostVisibility = () => {
        if (cfgUploadHost.value === 'imgbb') {
            groupImgbbKey.style.display = 'block';
        } else {
            groupImgbbKey.style.display = 'none';
        }
    };
    cfgUploadHost.addEventListener('change', updateHostVisibility);
    updateHostVisibility(); // init

    // --- Actions ---

    // 1. Scan Folder (reusable function)
    let scanInProgress = false;

    const doScan = async (folderPath) => {
        if (scanInProgress) return;
        scanInProgress = true;

        btnScan.disabled = true;
        btnScan.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg> 扫描中...`;

        try {
            // Parallel: scan files + extract tracklist
            const [scanRes, tracklistRes] = await Promise.all([
                fetch('/api/scan', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ folder_path: folderPath })
                }),
                fetch('/api/tracklist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ folder_path: folderPath })
                })
            ]);

            const scanData = await scanRes.json();
            const tracklistData = await tracklistRes.json();

            if (!scanRes.ok) {
                throw new Error(scanData.error || '扫描请求失败');
            }

            // Show scan results
            scanResultsDiv.classList.remove('hidden');

            if (scanData.albums.length === 0) {
                scanSummaryDiv.textContent = '未找到音频文件。';
                scanSummaryDiv.style.color = 'var(--error-color)';
                albumTreeDiv.innerHTML = '';
                btnGenerate.disabled = true;
                btnTorrentModal.disabled = true;
                tracklistSection.classList.add('hidden');
            } else {
                scanSummaryDiv.textContent = `找到 ${scanData.albums.length} 个专辑文件夹，共 ${scanData.total_tracks} 首曲目。`;
                scanSummaryDiv.style.color = 'var(--success-color)';

                albumTreeDiv.innerHTML = scanData.albums.map(album => `
                    <div class="tree-folder">
                        <div class="tree-folder-name">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
                            ${album.name}
                        </div>
                        <div class="tree-tracks">${album.count} 首曲目</div>
                    </div>
                `).join('');

                btnGenerate.disabled = false;
                btnTorrentModal.disabled = false;
            }

            // Show tracklist
            if (tracklistRes.ok && tracklistData.albums && tracklistData.albums.length > 0) {
                currentTracklistData = tracklistData.albums;
                renderTracklist(tracklistData.albums);
                tracklistSection.classList.remove('hidden');
            } else {
                tracklistSection.classList.add('hidden');
            }

        } catch (error) {
            showToast(`扫描出错: ${error.message}`, 'error');
            scanResultsDiv.classList.add('hidden');
            tracklistSection.classList.add('hidden');
            btnGenerate.disabled = true;
            btnTorrentModal.disabled = true;
        } finally {
            btnScan.disabled = false;
            btnScan.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> 扫描`;
            scanInProgress = false;
        }
    };

    btnScan.addEventListener('click', async () => {
        const folderPath = folderPathInput.value.trim();
        if (!folderPath) {
            showToast('请先输入音频文件夹路径', 'error');
            return;
        }
        doScan(folderPath);
    });

    // 2. Render Tracklist
    const renderTracklist = (albums) => {
        tracklistContent.innerHTML = albums.map(album => {
            const tracksHTML = album.tracks.map(t => `
                <tr>
                    <td class="track-num">${t.number.toString().padStart(2, '0')}</td>
                    <td>${t.title}</td>
                    <td class="track-duration">${t.duration_fmt}</td>
                </tr>
            `).join('');

            let audioInfo = '';
            if (album.audio_info && album.audio_info.sample_rate) {
                const sr = (album.audio_info.sample_rate / 1000).toFixed(1);
                const bd = album.audio_info.bits_per_sample;
                audioInfo = `${sr}kHz / ${bd}bit`;
            }

            return `
                <div class="tracklist-album">
                    <div class="tracklist-album-header">
                        <div>
                            <div class="tracklist-album-name">${album.album_name}</div>
                            <div class="tracklist-album-artist">${album.artist}${album.date ? ' · ' + album.date : ''}</div>
                        </div>
                        <div class="tracklist-album-meta">
                            ${audioInfo ? audioInfo + '<br>' : ''}${album.tracks.length} tracks
                        </div>
                    </div>
                    <table class="tracklist-table">
                        <thead><tr><th>#</th><th>Title</th><th style="text-align:right">Time</th></tr></thead>
                        <tbody>${tracksHTML}</tbody>
                    </table>
                    <div class="tracklist-total">
                        <span>${album.tracks.length} tracks</span>
                        <span>${album.total_duration_fmt}</span>
                    </div>
                </div>
            `;
        }).join('');
    };

    // 3. Format tabs for tracklist
    document.querySelectorAll('.format-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.format-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            selectedTracklistFormat = tab.dataset.format;
        });
    });

    // Copy tracklist
    btnCopyTracklist.addEventListener('click', async () => {
        if (!currentTracklistData) return;
        try {
            const res = await fetch('/api/tracklist/format', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    albums: currentTracklistData,
                    format: selectedTracklistFormat
                })
            });
            const data = await res.json();
            if (data.text) {
                await copyToClipboard(data.text, 'Tracklist 已复制');
            }
        } catch (e) {
            showToast('复制失败: ' + e.message, 'error');
        }
    });

    // 4. Generate Spectrograms
    btnGenerate.addEventListener('click', async () => {
        const folderPath = folderPathInput.value.trim();
        if (!folderPath) return;

        const autoUpload = cfgAutoUpload.checked;
        const host = cfgUploadHost.value;
        const apiKey = cfgImgbbKey.value.trim();

        // 仅 imgbb 需要 API Key，pixhost 无需
        if (autoUpload && host === 'imgbb' && !apiKey) {
            showToast('请先输入 imgbb API Key', 'error');
            cfgImgbbKey.focus();
            return;
        }

        // Collect config
        const config = {
            folder_path: folderPath,
            output_dir: outputDirInput.value.trim(),
            width: parseInt(cfgWidth.value) || 1920,
            height: parseInt(cfgHeight.value) || 400,
            dynamic_range: parseInt(cfgDynamicRange.value) || 90,
            gap: parseInt(cfgGap.value) || 2,
            direction: cfgDirection.value,
            show_labels: cfgLabels.checked,
            stitch: cfgStitch.checked,
            auto_upload: autoUpload,
            host: host,
            imgbb_api_key: autoUpload && cfgUploadHost.value === 'imgbb' ? apiKey : '',
        };

        btnGenerate.disabled = true;
        btnScan.disabled = true;
        btnTorrentModal.disabled = true;
        currentUploadResults = [];
        uploadResultsDiv.classList.add('hidden');
        resetProgress();
        addLog('提交生成任务...', 'info');

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || '无法启动生成任务');
            }

            addLog(`任务已启动 (ID: ${data.task_id})`, 'info');
            listenToProgress(data.task_id);

        } catch (error) {
            addLog(`请求失败: ${error.message}`, 'error');
            btnGenerate.disabled = false;
            btnScan.disabled = false;
        }
    });

    // 5. Listen to SSE Progress
    const listenToProgress = (taskId) => {
        if (currentEventSource) {
            currentEventSource.close();
        }

        const source = new EventSource(`/api/progress/${taskId}`);
        currentEventSource = source;

        source.onmessage = (event) => {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'album_start':
                    addLog(`开始处理: ${data.album} (${data.tracks_in_album} 首)`);
                    updateProgress(data.processed, data.total, `正在处理专辑: ${data.album}`);
                    break;
                case 'track_start':
                    updateProgress(data.processed, data.total, `正在生成: ${data.track}`);
                    break;
                case 'track_done':
                    updateProgress(data.processed, data.total, `生成中: ${data.track}`);
                    break;
                case 'track_error':
                    addLog(`曲目失败: ${data.track} — ${data.error}`, 'error');
                    updateProgress(data.processed, data.total, `失败: ${data.track}`);
                    break;
                case 'album_done':
                    addLog(`专辑拼接完成: ${data.output}`, 'success');
                    break;
                case 'upload_start':
                    addLog(`上传中: ${data.filename} (${data.index}/${data.total})`);
                    updateProgress(data.index - 1, data.total, `上传图床: ${data.filename}`);
                    addUploadItem(data.filename, 'uploading');
                    break;
                case 'upload_done':
                    addLog(`上传成功: ${data.filename} → ${data.url}`, 'success');
                    updateProgress(data.index, data.total, `上传完成: ${data.filename}`);
                    updateUploadItem(data.filename, 'success', data);
                    currentUploadResults.push(data);
                    break;
                case 'upload_error':
                    addLog(`上传失败: ${data.filename} — ${data.error}`, 'error');
                    updateUploadItem(data.filename, 'error', data);
                    break;
                case 'complete':
                    addLog(`所有任务完成！共生成 ${data.result.total_albums} 张拼接图。`, 'success');
                    updateProgress(data.result.total_tracks, data.result.total_tracks, '任务完成！');
                    btnGenerate.disabled = false;
                    btnScan.disabled = false;
                    source.close();
                    renderGallery(data.result.albums);
                    // Show upload results if any
                    if (currentUploadResults.length > 0) {
                        uploadResultsDiv.classList.remove('hidden');
                        showToast(`${currentUploadResults.length} 张图片已上传到图床`, 'success');
                    }
                    break;
                case 'error':
                    addLog(`发生错误: ${data.message}`, 'error');
                    btnGenerate.disabled = false;
                    btnScan.disabled = false;
                    btnTorrentModal.disabled = false;
                    source.close();
                    break;
                case 'end':
                    addLog('连接结束。', 'info');
                    btnGenerate.disabled = false;
                    btnScan.disabled = false;
                    btnTorrentModal.disabled = false;
                    source.close();
                    break;
            }
        };

        source.onerror = (error) => {
            console.error("SSE Error:", error);
            addLog('进度流连接中断', 'error');
            source.close();
            btnGenerate.disabled = false;
            btnScan.disabled = false;
            btnTorrentModal.disabled = false;
        };
    };

    // 6. Upload Results Management
    const addUploadItem = (filename, status) => {
        uploadResultsDiv.classList.remove('hidden');
        const item = document.createElement('div');
        item.className = `upload-link-item ${status}`;
        item.id = `upload-item-${filename.replace(/[^a-zA-Z0-9]/g, '_')}`;
        item.innerHTML = `
            <div class="upload-status-icon spin">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent-color)" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
            </div>
            <div class="upload-link-info">
                <div class="upload-link-name">${filename}</div>
                <div class="upload-link-url" style="color: var(--text-secondary)">上传中...</div>
            </div>
        `;
        uploadLinksDiv.appendChild(item);
    };

    const updateUploadItem = (filename, status, data) => {
        const itemId = `upload-item-${filename.replace(/[^a-zA-Z0-9]/g, '_')}`;
        const item = document.getElementById(itemId);
        if (!item) return;

        item.className = `upload-link-item ${status}`;

        if (status === 'success') {
            const url = data.direct_url || data.url;
            item.innerHTML = `
                <div class="upload-status-icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--success-color)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div class="upload-link-info">
                    <div class="upload-link-name">${filename}</div>
                    <div class="upload-link-url" onclick="window.open('${url}', '_blank')" title="点击打开">${url}</div>
                </div>
                <button class="upload-link-copy" onclick="event.stopPropagation(); copyLink(this, '${url}')" title="复制链接">复制</button>
            `;
        } else if (status === 'error') {
            item.innerHTML = `
                <div class="upload-status-icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--error-color)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                </div>
                <div class="upload-link-info">
                    <div class="upload-link-name">${filename}</div>
                    <div class="upload-link-url" style="color: var(--error-color)">${data.error || '上传失败'}</div>
                </div>
            `;
        }
    };

    // Global copy link function
    window.copyLink = async (btn, url) => {
        await copyToClipboard(url, '链接已复制');
        btn.textContent = '✓';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.textContent = '复制';
            btn.classList.remove('copied');
        }, 1500);
    };

    // 7. Link format tabs
    document.querySelectorAll('.link-format-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.link-format-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            selectedLinkFormat = tab.dataset.format;
        });
    });

    // Copy all links
    btnCopyAllLinks.addEventListener('click', async () => {
        if (currentUploadResults.length === 0) {
            showToast('没有可复制的链接', 'error');
            return;
        }

        const lines = currentUploadResults.map(r => {
            const url = r.direct_url || r.url;
            const name = r.filename || '';
            switch (selectedLinkFormat) {
                case 'bbcode':
                    return `[img]${url}[/img]`;
                case 'markdown':
                    return `![${name}](${url})`;
                case 'html':
                    return `<img src="${url}" alt="${name}">`;
                default:
                    return url;
            }
        });

        await copyToClipboard(lines.join('\n'), `${lines.length} 条链接已复制`);
    });

    // 8. Render Gallery
    const renderGallery = (albums) => {
        if (!albums || albums.length === 0) return;

        gallery.innerHTML = '';
        
        albums.forEach(album => {
            if (album.output) {
                // Stitched image
                const imgUrl = `/api/image?path=${encodeURIComponent(album.output)}`;
                const item = document.createElement('div');
                item.className = 'gallery-item';
                item.innerHTML = `
                    <div class="gallery-item-header">
                        <div class="gallery-item-title">${album.name}</div>
                        <div class="gallery-item-meta">${album.tracks} 首曲目</div>
                    </div>
                    <div class="gallery-item-img-wrap" onclick="openLightbox('${imgUrl}')">
                        <img src="${imgUrl}" alt="${album.name} 频谱图" loading="lazy">
                    </div>
                    <div class="gallery-item-actions">
                        <a href="${imgUrl}" download="${album.filename}" class="btn-download" onclick="event.stopPropagation()">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                            保存图片
                        </a>
                    </div>
                `;
                gallery.appendChild(item);
            } else if (album.tracks && album.tracks.length > 0) {
                // Individual tracks
                const albumHeader = document.createElement('h3');
                albumHeader.style.width = '100%';
                albumHeader.style.marginBottom = '10px';
                albumHeader.style.color = 'var(--text-main)';
                albumHeader.textContent = album.name;
                gallery.appendChild(albumHeader);

                album.tracks.forEach(track => {
                    const imgUrl = `/api/image?path=${encodeURIComponent(track.output)}`;
                    const item = document.createElement('div');
                    item.className = 'gallery-item';
                    item.innerHTML = `
                        <div class="gallery-item-header">
                            <div class="gallery-item-title">${track.name}</div>
                        </div>
                        <div class="gallery-item-img-wrap" onclick="openLightbox('${imgUrl}')">
                            <img src="${imgUrl}" alt="${track.name} 频谱图" loading="lazy">
                        </div>
                        <div class="gallery-item-actions">
                            <a href="${imgUrl}" download="${track.filename}" class="btn-download" onclick="event.stopPropagation()">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                                保存图片
                            </a>
                        </div>
                    `;
                    gallery.appendChild(item);
                });
            }
        });
    };

    // 9. Manual Upload Button (for already generated images)
    // This is triggered from the gallery if user wants to upload later

    // 10. Lightbox
    window.openLightbox = (src) => {
        lightboxImg.src = src;
        lightbox.classList.remove('hidden');
    };

    window.closeLightbox = (e) => {
        if (e.target === lightbox || e.target.classList.contains('lightbox-close')) {
            lightbox.classList.add('hidden');
            setTimeout(() => { lightboxImg.src = ''; }, 300);
        }
    };
    
    // Add some spin animation for loading
    const style = document.createElement('style');
    style.innerHTML = `
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .spin { animation: spin 1s linear infinite; }
        .spin svg { animation: spin 1s linear infinite; }
        
        #path-browser-list .pb-item {
            padding: 8px 12px;
            cursor: pointer;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        #path-browser-list .pb-item:hover {
            background-color: var(--hover-bg);
        }
        #path-browser-list .pb-item svg {
            color: var(--accent-color);
        }
    `;
    document.head.appendChild(style);

    // --- Path Browser Logic ---
    const pathBrowserModal = document.getElementById('path-browser-modal');
    const pathBrowserInput = document.getElementById('path-browser-input');
    const pathBrowserList = document.getElementById('path-browser-list');

    let currentBrowserPath = '';
    let browseRoot = '';  // 服务端配置的浏览根目录
    let debounceTimer = null;  // 用于手动输入路径时的防抖扫描
    let suppressAutoScan = false;  // 防止程序化修改路径时重复触发扫描

    window.closePathBrowser = () => {
        pathBrowserModal.classList.add('hidden');
    };

    btnBrowse.addEventListener('click', async () => {
        // 首次打开时获取 Browse Root
        if (!browseRoot) {
            try {
                const res = await fetch('/api/path');
                const data = await res.json();
                if (data.browse_root) {
                    browseRoot = data.browse_root;
                }
            } catch (e) {}
        }
        currentBrowserPath = folderPathInput.value.trim() || browseRoot || '/';
        loadPath(currentBrowserPath);
        pathBrowserModal.classList.remove('hidden');
    });

    window.confirmPathSelection = () => {
        suppressAutoScan = true;  // 防止设置 value 时触发 input 事件导致重复扫描
        folderPathInput.value = currentBrowserPath;
        suppressAutoScan = false;
        closePathBrowser();
        // 选中文件夹后自动触发扫描，无需再手动点击扫描按钮
        if (currentBrowserPath) {
            doScan(currentBrowserPath);
        }
    };

    // 手动输入路径时，防抖自动扫描（停止输入 600ms 后自动触发）
    folderPathInput.addEventListener('input', () => {
        if (suppressAutoScan) return;
        clearTimeout(debounceTimer);
        const val = folderPathInput.value.trim();
        if (!val) return;
        debounceTimer = setTimeout(() => {
            doScan(val);
        }, 600);
    });

    const loadPath = async (targetPath) => {
        try {
            pathBrowserList.innerHTML = '<div style="padding: 10px;">Loading...</div>';
            const res = await fetch(`/api/path?path=${encodeURIComponent(targetPath)}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to load path');

            currentBrowserPath = data.path;
            pathBrowserInput.value = data.path;
            if (data.browse_root) {
                browseRoot = data.browse_root;
            }

            if (data.entries.length === 0) {
                pathBrowserList.innerHTML = '<div style="padding: 10px; color: var(--text-secondary);">空目录</div>';
                return;
            }

            pathBrowserList.innerHTML = data.entries.map(entry => {
                const icon = entry.is_dir
                    ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>`
                    : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>`;

                return `
                    <div class="pb-item" onclick="${entry.is_dir ? `window.navPath('${entry.path.replace(/\\/g, '\\\\')}')` : ''}">
                        ${icon}
                        <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${entry.name}</span>
                    </div>
                `;
            }).join('');
        } catch (e) {
            pathBrowserList.innerHTML = `<div style="padding: 10px; color: var(--error-color);">${e.message}</div>`;
        }
    };

    window.navPath = (path) => {
        loadPath(path);
    };

    // --- Torrent Logic ---
    const torrentModal = document.getElementById('torrent-modal');
    const torrentTrackers = document.getElementById('torrent-trackers');
    const torrentSource = document.getElementById('torrent-source');
    const torrentPrivate = document.getElementById('torrent-private');
    const btnCreateTorrent = document.getElementById('btn-create-torrent');

    window.closeTorrentModal = () => {
        torrentModal.classList.add('hidden');
    };

    btnTorrentModal.addEventListener('click', () => {
        torrentModal.classList.remove('hidden');
    });

    btnCreateTorrent.addEventListener('click', async () => {
        const folderPath = folderPathInput.value.trim();
        if (!folderPath) {
            showToast('请先选择文件夹路径', 'error');
            return;
        }

        const config = {
            folder_path: folderPath,
            output_dir: outputDirInput.value.trim() || null,
            trackers: torrentTrackers.value,
            source: torrentSource.value,
            private: torrentPrivate.checked
        };

        btnCreateTorrent.disabled = true;
        closeTorrentModal();
        resetProgress();
        progressSection.classList.remove('hidden');
        addLog('提交制种任务...', 'info');

        try {
            const res = await fetch('/api/torrent', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.error || '制种失败');

            addLog(`任务已启动 (ID: ${data.task_id})`, 'info');
            listenToTorrentProgress(data.task_id);
        } catch (e) {
            addLog(`请求失败: ${e.message}`, 'error');
            btnCreateTorrent.disabled = false;
        }
    });

    const listenToTorrentProgress = (taskId) => {
        if (currentEventSource) {
            currentEventSource.close();
        }

        const source = new EventSource(`/api/progress/${taskId}`);
        currentEventSource = source;

        source.onmessage = (event) => {
            const data = JSON.parse(event.data);

            switch (data.type) {
                case 'torrent_start':
                    addLog(data.message);
                    updateProgress(0, 100, data.message);
                    break;
                case 'torrent_progress':
                    if (data.percent !== undefined) {
                        updateProgress(data.percent, 100, data.message);
                    } else {
                        updateProgress(0, 100, data.message);
                    }
                    break;
                case 'torrent_done':
                    addLog(`制种完成: ${data.output}`, 'success');
                    updateProgress(100, 100, '制种完成！');
                    break;
                case 'complete':
                    btnCreateTorrent.disabled = false;
                    source.close();
                    const torrentUrl = `/api/output-files`; // Provide a way to download, let's just show success for now
                    showToast('种子已在输出目录生成', 'success');
                    break;
                case 'error':
                    addLog(`错误: ${data.message}`, 'error');
                    btnCreateTorrent.disabled = false;
                    source.close();
                    break;
                case 'end':
                    btnCreateTorrent.disabled = false;
                    source.close();
                    break;
            }
        };

        source.onerror = (error) => {
            addLog('进度流连接中断', 'error');
            source.close();
            btnCreateTorrent.disabled = false;
        };
    };
});

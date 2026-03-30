document.addEventListener('DOMContentLoaded', () => {
    const scrapeForm = document.getElementById('scrape-form');
    const urlInput = document.getElementById('url-input');
    const scrapeBtn = document.getElementById('scrape-btn');
    const resultsSection = document.getElementById('results-section');
    const imageGrid = document.getElementById('image-grid');
    const errorMsg = document.getElementById('error-message');
    const selectAllBtn = document.getElementById('select-all-btn');
    const downloadBtn = document.getElementById('download-btn');

    let scrapedImages = [];
    let selectedUrls = new Set();

    scrapeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (!url) return;

        // Reset UI
        toggleLoading(scrapeBtn, true);
        errorMsg.classList.add('hidden');
        resultsSection.classList.add('hidden');
        imageGrid.innerHTML = '';
        selectedUrls.clear();

        try {
            const res = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.error || 'Failed to scrape website');
            }

            scrapedImages = data.images;
            
            if (scrapedImages.length === 0) {
                throw new Error('No images could be extracted from this URL.');
            }

            renderGrid();
            resultsSection.classList.remove('hidden');

            // Scroll to results smoothly
            setTimeout(() => {
                resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);

        } catch (err) {
            errorMsg.textContent = err.message;
            errorMsg.classList.remove('hidden');
        } finally {
            toggleLoading(scrapeBtn, false);
        }
    });

    function renderGrid() {
        scrapedImages.forEach(({url, info}, idx) => {
            const card = document.createElement('div');
            card.className = 'image-card selected'; // Default selected
            selectedUrls.add(url);
            
            let infoHtml = '';
            if (info) {
                // Formatting newlines into breaks nicely for UI layout, cap the length slightly for very long infos
                const displayInfo = info.length > 200 ? info.substring(0, 197) + '...' : info;
                infoHtml = `<div class="image-info">${displayInfo.replace(/\\n/g, '<br>')}</div>`;
            }

            card.innerHTML = `
                <div class="checkbox-overlay"></div>
                ${infoHtml}
                <img src="${url}" alt="Extracted asset" loading="lazy" onerror="this.parentElement.style.display='none';">
            `;

            card.addEventListener('click', () => {
                if (selectedUrls.has(url)) {
                    selectedUrls.delete(url);
                    card.classList.remove('selected');
                } else {
                    selectedUrls.add(url);
                    card.classList.add('selected');
                }
                updateActionButtons();
            });

            imageGrid.appendChild(card);
        });
        updateActionButtons();
    }

    selectAllBtn.addEventListener('click', () => {
        const visibleCards = Array.from(imageGrid.querySelectorAll('.image-card')).filter(card => card.style.display !== 'none');
        const currentlySelected = selectedUrls.size;
        
        // If anything is unselected, select all. Otherwise, deselect all.
        const shouldSelectAll = currentlySelected < visibleCards.length;

        visibleCards.forEach((card) => {
            const imgEl = card.querySelector('img');
            const url = imgEl.src;
            
            if (shouldSelectAll) {
                selectedUrls.add(url);
                card.classList.add('selected');
            } else {
                selectedUrls.delete(url);
                card.classList.remove('selected');
            }
        });
        
        updateActionButtons();
    });

    function updateActionButtons() {
        // Update Download button text and state
        if (selectedUrls.size === 0) {
            downloadBtn.style.opacity = '0.5';
            downloadBtn.style.pointerEvents = 'none';
            downloadBtn.querySelector('.btn-text').textContent = 'Select Assets';
            selectAllBtn.textContent = 'Select All';
        } else {
            downloadBtn.style.opacity = '1';
            downloadBtn.style.pointerEvents = 'auto';
            downloadBtn.querySelector('.btn-text').textContent = `Download ZIP (${selectedUrls.size})`;
            
            const visibleCardsCount = Array.from(imageGrid.querySelectorAll('.image-card')).filter(c => c.style.display !== 'none').length;
            if (selectedUrls.size === visibleCardsCount) {
                selectAllBtn.textContent = 'Deselect All';
            } else {
                selectAllBtn.textContent = 'Select All';
            }
        }
    }

    downloadBtn.addEventListener('click', async () => {
        if (selectedUrls.size === 0) return;

        toggleLoading(downloadBtn, true);

        try {
            // Gather correct items for selected URLs
            const downloadItems = Array.from(selectedUrls).map(url => {
                const imgObj = scrapedImages.find(img => img.url === url);
                return imgObj ? imgObj : { url: url, info: '' };
            });

            const res = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ items: downloadItems })
            });

            if (!res.ok) {
                throw new Error('Failed to assemble ZIP file on server.');
            }

            // Trigger silent file download via DOM element
            const blob = await res.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = 'gravitas_extraction.zip';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(downloadUrl);
            document.body.removeChild(a);

        } catch (err) {
            alert("Download Error: " + err.message);
        } finally {
            toggleLoading(downloadBtn, false);
        }
    });

    function toggleLoading(btn, isLoading) {
        const textArea = btn.querySelector('.btn-text');
        const loader = btn.querySelector('.loader');
        
        if (isLoading) {
            textArea.classList.add('hidden');
            loader.classList.remove('hidden');
            btn.style.pointerEvents = 'none';
        } else {
            textArea.classList.remove('hidden');
            loader.classList.add('hidden');
            btn.style.pointerEvents = 'auto';
        }
    }
});

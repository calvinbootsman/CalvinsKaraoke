window.createKaraokeLyricWindow = function createKaraokeLyricWindow(options) {
    const lyricsEl = options.lyricsEl;
    const visibleLines = Number(options.visibleLines || 6);
    const activeClassName = String(options.activeClassName || 'active');
    const lineClassName = String(options.lineClassName || 'line');
    const emptyMessage = String(options.emptyMessage || 'No synced lyrics found.');
    const smoothScroll = options.smoothScroll !== false;

    let lyricRows = [];
    let activeIndex = -1;

    function renderRows(startIndex) {
        lyricsEl.innerHTML = '';
        const endIndex = Math.min(startIndex + visibleLines, lyricRows.length);
        for (let i = startIndex; i < endIndex; i += 1) {
            const row = lyricRows[i];
            const line = document.createElement('div');
            line.className = lineClassName;
            line.textContent = String(row.text || '');
            line.dataset.index = String(i);
            lyricsEl.appendChild(line);
        }
    }

    function setRows(rows) {
        lyricRows = Array.isArray(rows) ? rows : [];
        activeIndex = -1;
        if (!lyricRows.length) {
            lyricsEl.innerHTML = `<div style="color:#94a3b8; font-size:0.92rem; line-height:1.6;">${emptyMessage}</div>`;
            return;
        }
        renderRows(0);
    }

    function highlight(currentTime) {
        if (!lyricRows.length) return;

        let index = -1;
        for (let i = 0; i < lyricRows.length; i += 1) {
            if (Number(currentTime || 0) >= Number(lyricRows[i].time || 0)) {
                index = i;
            } else {
                break;
            }
        }

        if (index === activeIndex) return;

        const maxStart = Math.max(0, lyricRows.length - visibleLines);
        const startIndex = index <= 0 ? 0 : Math.min(Math.max(0, index - 1), maxStart);
        renderRows(startIndex);

        const children = lyricsEl.children;
        const activeChildIndex = index - startIndex;
        if (activeChildIndex >= 0 && activeChildIndex < children.length) {
            children[activeChildIndex].classList.add(activeClassName);
            if (smoothScroll) {
                children[activeChildIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }

        activeIndex = index;
    }

    return {
        setRows,
        highlight,
    };
};
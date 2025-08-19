document.addEventListener('DOMContentLoaded', () => {
    // --- STATE ---
    const state = {
        images: [],
        currentIndex: 0,
        settings: {},
    };

    // --- DOM ELEMENTS ---
    const- canvasLeft = document.getElementById('canvas-left');
    const canvasRight = document.getElementById('canvas-right');
    const ctxLeft = canvasLeft.getContext('2d');
    const ctxRight = canvasRight.getContext('2d');

    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const jumpBtn = document.getElementById('jump-btn');
    const refreshBtn = document.getElementById('refresh-btn');
    const statusLabel = document.getElementById('status-label');

    const createBookBtn = document.getElementById('create-book-btn');
    const bookNameInput = document.getElementById('book-name-input');
    const transferBtn = document.getElementById('transfer-btn');

    const statsPending = document.getElementById('stats-pending');
    const statsBooksToday = document.getElementById('stats-books-today');
    const statsTotalToday = document.getElementById('stats-total-today');

    // --- API FUNCTIONS ---
    const api = {
        get: (url) => fetch(url).then(res => res.ok ? res.json() : Promise.reject(res)),
        post: (url, data) => fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        }).then(res => res.ok ? res.json() : Promise.reject(res)),
    };

    const fetchImages = async () => {
        try {
            const data = await api.get('/api/images');
            state.images = data.images || [];
            renderAll();
        } catch (error) {
            console.error('Failed to fetch images:', error);
            statusLabel.textContent = 'Error fetching images.';
        }
    };

    const fetchStats = async () => {
        try {
            const stats = await api.get('/api/stats');
            statsPending.textContent = `Pending Scans: ${stats.pages_in_scan_folder}`;
            statsBooksToday.textContent = `Books Today: ${stats.books_in_today_folder} (${stats.pages_in_today_folder} pages)`;
            statsTotalToday.textContent = `Total Pages Today: ${stats.total_pages_today}`;
        } catch (error) {
            console.error('Failed to fetch stats:', error);
        }
    };

    const fetchConfig = async () => {
        try {
            const config = await api.get('/api/config');
            state.settings = config;
            document.getElementById('scan-folder').value = config.scan;
            document.getElementById('today-folder').value = config.today;
        } catch (error)            {
            console.error('Failed to fetch config:', error);
        }
    }


    // --- RENDERING ---
    const renderImages = () => {
        const drawImage = (ctx, canvas, imagePath) => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (!imagePath) return;

            const img = new Image();
            img.onload = () => {
                // Scale image to fit canvas
                const hRatio = canvas.width / img.width;
                const vRatio = canvas.height / img.height;
                const ratio = Math.min(hRatio, vRatio);
                const centerShift_x = (canvas.width - img.width * ratio) / 2;
                const centerShift_y = (canvas.height - img.height * ratio) / 2;
                ctx.drawImage(img, 0, 0, img.width, img.height,
                              centerShift_x, centerShift_y, img.width * ratio, img.height * ratio);
            };
            img.onerror = () => {
                ctx.fillStyle = 'red';
                ctx.fillText('Error loading image.', 10, 20);
            };
            // Use the /images static route we set up in the backend
            img.src = `/images/${imagePath}`;
        };

        const leftImageName = state.images[state.currentIndex];
        const rightImageName = state.images[state.currentIndex + 1];

        drawImage(ctxLeft, canvasLeft, leftImageName);
        drawImage(ctxRight, canvasRight, rightImageName);
        updateStatusLabel();
    };

    const renderAll = () => {
        renderImages();
        fetchStats();
    };

    const updateStatusLabel = () => {
        if (state.images.length === 0) {
            statusLabel.textContent = "Waiting for images...";
            return;
        }
        const first = state.currentIndex + 1;
        const second = state.currentIndex + 2 > state.images.length ? '' : `-${state.currentIndex + 2}`;
        statusLabel.textContent = `Pages ${first}${second} of ${state.images.length}`;
    };


    // --- WEBSOCKET ---
    const setupWebSocket = () => {
        const ws = new WebSocket(`ws://${window.location.host}/ws/new-images`);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('WebSocket message received:', data);
            if (data.type === 'new_image' || data.type === 'refresh') {
                // A new image has arrived, or a deletion happened. Re-fetch the list.
                const wasAtEnd = state.currentIndex >= state.images.length - 2;
                fetchImages().then(() => {
                    if (wasAtEnd) {
                        // If we were at the end, jump to the new end
                        jumpToEnd();
                    }
                });
            }
        };

        ws.onopen = () => console.log('WebSocket connection established.');
        ws.onclose = () => {
            console.log('WebSocket connection closed. Retrying in 3 seconds.');
            setTimeout(setupWebSocket, 3000);
        };
        ws.onerror = (error) => console.error('WebSocket error:', error);
    };

    // --- EVENT HANDLERS ---
    const jumpToEnd = () => {
        if (state.images.length > 0) {
            state.currentIndex = Math.max(0, state.images.length - 2);
        }
        renderImages();
    };

    prevBtn.addEventListener('click', () => {
        if (state.currentIndex > 0) {
            state.currentIndex -= 2;
            renderImages();
        }
    });

    nextBtn.addEventListener('click', () => {
        if (state.currentIndex + 2 < state.images.length) {
            state.currentIndex += 2;
            renderImages();
        }
    });

    jumpBtn.addEventListener('click', jumpToEnd);

    refreshBtn.addEventListener('click', () => {
        fetchImages();
        fetchStats();
    });

    createBookBtn.addEventListener('click', async () => {
        const bookName = bookNameInput.value.trim();
        if (!bookName) {
            alert('Please enter a book name.');
            return;
        }
        try {
            const result = await api.post('/api/books', { book_name: bookName });
            alert(result.message);
            bookNameInput.value = '';
            fetchImages(); // Refresh image list
        } catch (error) {
            console.error('Failed to create book:', error);
            alert('Error creating book.');
        }
    });

    transferBtn.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to transfer all books in the "Today" folder to their final data destinations?')) {
            return;
        }
        try {
            const result = await api.post('/api/transfer', {});
            alert(result.message);
            fetchStats(); // Refresh stats
        } catch (error) {
            console.error('Failed to transfer books:', error);
            alert('Error transferring books.');
        }
    });

    // --- INITIALIZATION ---
    const init = async () => {
        await fetchConfig();
        await fetchImages();
        setupWebSocket();
    };

    init();
});

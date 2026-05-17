/* =============================================================================
 * APP.JS — Frontend interactif
 *   - Carte Leaflet (centrée sur UEMF Fès) avec drones / stations / orders
 *   - WebSocket → push temps réel depuis FastAPI
 *   - Chart.js → graphiques de performance
 *   - Animations CSS pour les drones (hélices, halo, batterie SVG)
 * ============================================================================= */

(() => {
    // ===== ETAT GLOBAL =====
    const state = {
        ws: null,
        wsReconnect: 0,
        map: null,
        markers: {
            drones: {},
            stations: {},
            customers: {},
            routes: {},
        },
        charts: {
            success: null,
            performance: null,
        },
        history: {
            timestamps: [],
            delivered: [],
            failed: [],
            active: [],
        },
        geoMeta: null,
    };

    // ===== INIT =====
    document.addEventListener('DOMContentLoaded', async () => {
        startClock();
        await loadGeoMetadata();
        initMap();
        initCharts();
        initOrderForm();
        connectWebSocket();
    });

    // =========================================================================
    // 1) HORLOGE
    // =========================================================================
    function startClock() {
        const tick = () => {
            const now = new Date();
            const hh = String(now.getHours()).padStart(2, '0');
            const mm = String(now.getMinutes()).padStart(2, '0');
            const ss = String(now.getSeconds()).padStart(2, '0');
            document.getElementById('clock').textContent = `${hh}:${mm}:${ss}`;
        };
        tick();
        setInterval(tick, 1000);
    }

    // =========================================================================
    // 2) Métadonnées GPS (zone Fès UEMF)
    // =========================================================================
    async function loadGeoMetadata() {
        try {
            const res = await fetch('/api/geo');
            state.geoMeta = await res.json();
        } catch (e) {
            console.warn('Geo metadata KO, fallback UEMF', e);
            state.geoMeta = {
                center: { lat: 33.9716, lon: -5.0091 },
                bounds: { south: 33.9536, north: 33.9896, west: -5.0311, east: -4.9871 },
                grid: { width: 50, height: 50 },
                campus_name: 'UEMF Fès',
            };
        }
    }

    // =========================================================================
    // 3) CARTE LEAFLET (dark theme + drones animés)
    // =========================================================================
    function initMap() {
        const { center, bounds } = state.geoMeta;

        state.map = L.map('map', {
            center: [center.lat, center.lon],
            zoom: 15,            // dézoomé pour voir TOUS les drones (zone 3km)
            zoomControl: true,
            attributionControl: true,
            preferCanvas: false,
            layers: [],
        });

        // Auto-ajustement aux limites de la zone d'opération
        // pour cadrer parfaitement les 5 drones + 3 stations dès le départ
        if (state.geoMeta.bounds) {
            const b = state.geoMeta.bounds;
            state.map.fitBounds(
                [[b.south, b.west], [b.north, b.east]],
                { padding: [30, 30] }
            );
        }

        // ===== CARTE STYLE GOOGLE MAPS HYBRIDE =====
        // Couche 1 (BASE) : Imagerie satellite haute résolution Esri World Imagery
        // → photos aériennes/satellite réelles
        const satellite = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {
                attribution: 'Imagerie © Esri · Maxar · Earthstar Geographics',
                maxZoom: 19,
                maxNativeZoom: 19,
            }
        ).addTo(state.map);

        // Couche 2 (OVERLAY) : Labels CartoDB Voyager (transparent par-dessus la satellite)
        // → noms de rues + villes en blanc avec halo, fond TRANSPARENT
        const labelsOverlay = L.tileLayer(
            'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png',
            {
                subdomains: 'abcd',
                maxZoom: 20,
                pane: 'shadowPane',   // au-dessus des tuiles base
            }
        ).addTo(state.map);

        // Alternative : carte couleur classique (vue plan)
        const colorMap = L.tileLayer(
            'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
            { subdomains: 'abcd', maxZoom: 20 }
        );

        // Vue OpenStreetMap classique
        const osmStreets = L.tileLayer(
            'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            { subdomains: 'abc', maxZoom: 19 }
        );

        // Contrôle de couches : 3 vues au choix
        const baseLayers = {
            '🛰️ Satellite HD': satellite,
            '🗺️ Carte couleur': colorMap,
            '📍 OpenStreetMap': osmStreets,
        };
        const overlayLayers = {
            'Noms de rues': labelsOverlay,
        };
        L.control.layers(baseLayers, overlayLayers, {
            position: 'topright',
            collapsed: false,
        }).addTo(state.map);

        // Cadre de la zone d'opération
        const boundsRect = L.rectangle(
            [[bounds.south, bounds.west], [bounds.north, bounds.east]],
            {
                color: '#22d3ee',
                weight: 1.5,
                fillOpacity: 0.02,
                dashArray: '4 6',
                interactive: false,
            }
        ).addTo(state.map);

        // Marqueur UEMF (centre)
        const uemfIcon = L.divIcon({
            className: '',
            html: `
                <div class="customer-marker" style="color:#22d3ee;">
                    <div class="body" style="border-radius:8px;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 21h18M5 21V7l7-4 7 4v14"/>
                            <path d="M9 21V12h6v9"/>
                        </svg>
                    </div>
                </div>`,
            iconSize: [26, 26],
            iconAnchor: [13, 13],
        });
        L.marker([center.lat, center.lon], { icon: uemfIcon, zIndexOffset: -100 })
            .addTo(state.map)
            .bindPopup(`<b style="color:#22d3ee">🎓 ${state.geoMeta.campus_name}</b>`);
    }

    // =========================================================================
    // 4) CHART.JS — Success rate + Performance over time
    // =========================================================================
    function initCharts() {
        // Couleurs partagées
        Chart.defaults.font.family = "'Inter', sans-serif";
        Chart.defaults.color = '#94a3b8';

        // ----- Donut "Taux de réussite" -----
        const ctxSuccess = document.getElementById('success-chart').getContext('2d');
        state.charts.success = new Chart(ctxSuccess, {
            type: 'doughnut',
            data: {
                labels: ['Livrées', 'Échecs'],
                datasets: [{
                    data: [0, 0],
                    backgroundColor: ['#34d399', '#fb7185'],
                    borderColor: '#0c1020',
                    borderWidth: 2,
                    cutout: '70%',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { boxWidth: 8, font: { size: 10 } },
                    },
                    tooltip: {
                        backgroundColor: 'rgba(12, 16, 32, 0.95)',
                        titleColor: '#e2e8f0',
                        bodyColor: '#94a3b8',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                    },
                },
            },
        });

        // ----- Line "Performance" -----
        const ctxPerf = document.getElementById('performance-chart').getContext('2d');
        state.charts.performance = new Chart(ctxPerf, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Livrées',
                        data: [],
                        borderColor: '#34d399',
                        backgroundColor: 'rgba(52, 211, 153, 0.15)',
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                    {
                        label: 'Actives',
                        data: [],
                        borderColor: '#fbbf24',
                        backgroundColor: 'rgba(251, 191, 36, 0.10)',
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 400 },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { boxWidth: 8, font: { size: 10 }, padding: 8 },
                    },
                    tooltip: {
                        backgroundColor: 'rgba(12, 16, 32, 0.95)',
                        titleColor: '#e2e8f0',
                        bodyColor: '#94a3b8',
                    },
                },
                scales: {
                    x: {
                        display: false,
                        grid: { color: 'rgba(255,255,255,0.04)' },
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { font: { size: 9 }, stepSize: 1 },
                        grid: { color: 'rgba(255,255,255,0.04)' },
                    },
                },
            },
        });
    }

    // =========================================================================
    // 5) WEBSOCKET
    // =========================================================================
    function connectWebSocket() {
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${window.location.host}/ws`;
        console.log('🔌 Connexion WebSocket →', url);
        state.ws = new WebSocket(url);

        state.ws.onopen = () => {
            setConnection('connected');
            state.wsReconnect = 0;
        };

        state.ws.onmessage = (event) => {
            try {
                const snapshot = JSON.parse(event.data);
                updateUI(snapshot);
            } catch (e) {
                console.error('WS parse error', e);
            }
        };

        state.ws.onerror = (e) => console.warn('WS error', e);

        state.ws.onclose = () => {
            setConnection('disconnected');
            state.wsReconnect++;
            const delay = Math.min(5000, 1000 * state.wsReconnect);
            console.log(`🔁 Reconnexion dans ${delay}ms...`);
            setTimeout(connectWebSocket, delay);
        };
    }

    function setConnection(status) {
        const dot = document.getElementById('connection-dot');
        const text = document.getElementById('connection-text');
        const pill = document.getElementById('connection-pill');
        if (status === 'connected') {
            dot.className = 'w-2 h-2 rounded-full bg-emerald-400 pulse-dot';
            text.textContent = 'CONNECTÉ';
            text.classList.remove('text-rose-400');
            text.classList.add('text-emerald-400');
            pill.classList.remove('border-rose-500/40');
            pill.classList.add('border-emerald-500/40');
        } else {
            dot.className = 'w-2 h-2 rounded-full bg-rose-400';
            text.textContent = 'DÉCONNECTÉ';
            text.classList.add('text-rose-400');
            text.classList.remove('text-emerald-400');
            pill.classList.add('border-rose-500/40');
            pill.classList.remove('border-emerald-500/40');
        }
    }

    // =========================================================================
    // 6) MISE A JOUR UI
    // =========================================================================
    function updateUI(snap) {
        updateStats(snap.stats);
        updateWeather(snap.weather);
        updateDronesOnMap(snap.drones);
        updateStationsOnMap(snap.stations);
        updateCustomersOnMap(snap.customers);
        updateOrdersOnMap(snap.orders);
        updateFleetPanel(snap.drones);
        updateOrdersPanel(snap.orders);
        updateEventsLog(snap.events);
        updateCharts(snap.stats);
    }

    // ---- STATS ----
    function updateStats(stats) {
        document.getElementById('stat-total').textContent = stats.total_orders;
        document.getElementById('stat-active').textContent = stats.active_orders;
        document.getElementById('stat-delivered').textContent = stats.deliveries_completed;
        document.getElementById('stat-failed').textContent = stats.deliveries_failed;
    }

    // ---- WEATHER PILL ----
    function updateWeather(weather) {
        const icons = {
            clear: '☀ CLEAR', windy: '🌬 WINDY',
            rainy: '🌧 RAINY', stormy: '⛈ STORMY',
        };
        document.getElementById('weather-pill').textContent =
            icons[weather] || weather.toUpperCase();
    }

    // ---- DRONES ON MAP ----
    function updateDronesOnMap(drones) {
        const seen = new Set();
        for (const [jid, info] of Object.entries(drones)) {
            seen.add(jid);
            if (!info.lat || !info.lon) continue;

            let marker = state.markers.drones[jid];
            if (!marker) {
                marker = createDroneMarker(jid, info);
                state.markers.drones[jid] = marker;
                marker.addTo(state.map);
            } else {
                marker.setLatLng([info.lat, info.lon]);
                updateDroneIcon(marker, jid, info);
            }
        }
        // Suppression des drones disparus
        for (const jid in state.markers.drones) {
            if (!seen.has(jid)) {
                state.map.removeLayer(state.markers.drones[jid]);
                delete state.markers.drones[jid];
            }
        }
    }

    function createDroneMarker(jid, info) {
        const icon = L.divIcon({
            className: '',
            html: buildDroneHtml(jid, info),
            iconSize: [64, 64],
            iconAnchor: [32, 32],
        });
        return L.marker([info.lat, info.lon], { icon, zIndexOffset: 1000 })
            .bindTooltip(jid.split('@')[0], {
                permanent: false, direction: 'top', offset: [0, -28],
                className: 'drone-tooltip',
            });
    }

    function updateDroneIcon(marker, jid, info) {
        marker.setIcon(L.divIcon({
            className: '',
            html: buildDroneHtml(jid, info),
            iconSize: [64, 64],
            iconAnchor: [32, 32],
        }));
    }

    function buildDroneHtml(jid, info) {
        const status = info.status || 'idle';
        const battery = info.battery || 0;
        const profile = info.profile || {};
        // Nom = profil (FALCON, VOYAGER...) ou fallback drone1, drone2
        const name = profile.name || jid.split('@')[0].toUpperCase();
        const icon = profile.icon || '';
        const batteryColor = battery < 25 ? '#fb7185'
                          : battery < 60 ? '#fbbf24'
                          : '#34d399';
        const batteryPct = battery / 100;
        const ringR = 28;
        const circumference = 2 * Math.PI * ringR;
        const dashOffset = circumference * (1 - batteryPct);

        // Identifiant unique pour les gradients SVG (évite collisions entre drones)
        const gid = `g-${jid.replace(/[@.]/g, '-')}`;

        // Le carrying status affiche en plus une caisse rouge sous le drone
        const cargoIndicator = status === 'carrying'
            ? `<div class="cargo-box"></div>` : '';

        // Drone TACTICAL PRO style DJI Phantom (vue de dessus avec relief 3D)
        return `
            <div class="drone-marker ${status}" data-name="${name}">
                <div class="drone-shadow"></div>
                <div class="drone-label">${icon}${icon ? ' ' : ''}${name}</div>
                <div class="pulse"></div>

                <!-- Anneau de batterie SVG (rotation -90° pour démarrer en haut) -->
                <svg class="battery-ring" width="64" height="64" viewBox="0 0 64 64">
                    <circle cx="32" cy="32" r="${ringR}" stroke="rgba(0,0,0,0.45)" stroke-width="3" fill="none"/>
                    <circle cx="32" cy="32" r="${ringR}"
                        stroke="${batteryColor}"
                        stroke-width="3"
                        stroke-linecap="round"
                        stroke-dasharray="${circumference}"
                        stroke-dashoffset="${dashOffset}"
                        fill="none"
                        style="filter: drop-shadow(0 0 6px ${batteryColor})"/>
                </svg>

                <!-- Châssis du drone (SVG avec gradients pour relief 3D) -->
                <svg class="drone-body" width="56" height="56" viewBox="0 0 60 60">
                    <defs>
                        <radialGradient id="${gid}-body" cx="50%" cy="35%" r="65%">
                            <stop offset="0%" stop-color="#64748b"/>
                            <stop offset="50%" stop-color="#334155"/>
                            <stop offset="100%" stop-color="#0f172a"/>
                        </radialGradient>
                        <linearGradient id="${gid}-arm" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#334155"/>
                            <stop offset="100%" stop-color="#0f172a"/>
                        </linearGradient>
                        <radialGradient id="${gid}-motor" cx="50%" cy="40%">
                            <stop offset="0%" stop-color="#475569"/>
                            <stop offset="100%" stop-color="#0f172a"/>
                        </radialGradient>
                        <radialGradient id="${gid}-cam" cx="40%" cy="40%">
                            <stop offset="0%" stop-color="#94a3b8"/>
                            <stop offset="40%" stop-color="#1e293b"/>
                            <stop offset="100%" stop-color="#000"/>
                        </radialGradient>
                    </defs>

                    <!-- Halo de couleur du status (autour du body) -->
                    <circle cx="30" cy="30" r="14" fill="currentColor" opacity="0.18"/>

                    <!-- 4 BRAS du drone (épais avec dégradé métallique) -->
                    <line x1="30" y1="30" x2="10" y2="10" stroke="url(#${gid}-arm)" stroke-width="6" stroke-linecap="round"/>
                    <line x1="30" y1="30" x2="50" y2="10" stroke="url(#${gid}-arm)" stroke-width="6" stroke-linecap="round"/>
                    <line x1="30" y1="30" x2="10" y2="50" stroke="url(#${gid}-arm)" stroke-width="6" stroke-linecap="round"/>
                    <line x1="30" y1="30" x2="50" y2="50" stroke="url(#${gid}-arm)" stroke-width="6" stroke-linecap="round"/>

                    <!-- Trait de surbrillance sur les bras (effet métal poli) -->
                    <line x1="30" y1="30" x2="10" y2="10" stroke="rgba(255,255,255,0.18)" stroke-width="1.5"/>
                    <line x1="30" y1="30" x2="50" y2="10" stroke="rgba(255,255,255,0.18)" stroke-width="1.5"/>
                    <line x1="30" y1="30" x2="10" y2="50" stroke="rgba(255,255,255,0.18)" stroke-width="1.5"/>
                    <line x1="30" y1="30" x2="50" y2="50" stroke="rgba(255,255,255,0.18)" stroke-width="1.5"/>

                    <!-- BODY central (hull) avec dégradé radial -->
                    <circle cx="30" cy="30" r="11" fill="url(#${gid}-body)" stroke="currentColor" stroke-width="1.5"/>
                    <!-- Trait de surbrillance en haut (effet 3D, lumière du haut) -->
                    <path d="M 22,26 A 9,9 0 0 1 38,26" stroke="rgba(255,255,255,0.25)" stroke-width="1" fill="none"/>

                    <!-- CAMERA GIMBAL au centre (lentille avec reflet) -->
                    <circle cx="30" cy="30" r="6" fill="url(#${gid}-cam)" stroke="currentColor" stroke-width="0.6"/>
                    <circle cx="30" cy="30" r="3.5" fill="#0f172a"/>
                    <circle cx="29" cy="29" r="1.2" fill="rgba(255,255,255,0.55)"/>

                    <!-- ANTENNE GPS en haut -->
                    <line x1="30" y1="19" x2="30" y2="14" stroke="currentColor" stroke-width="1.5"/>
                    <circle cx="30" cy="13" r="1.8" fill="currentColor"/>

                    <!-- 4 MOTEURS aux extrémités (cylindres) -->
                    <circle cx="10" cy="10" r="6" fill="url(#${gid}-motor)" stroke="currentColor" stroke-width="1.5"/>
                    <circle cx="50" cy="10" r="6" fill="url(#${gid}-motor)" stroke="currentColor" stroke-width="1.5"/>
                    <circle cx="10" cy="50" r="6" fill="url(#${gid}-motor)" stroke="currentColor" stroke-width="1.5"/>
                    <circle cx="50" cy="50" r="6" fill="url(#${gid}-motor)" stroke="currentColor" stroke-width="1.5"/>

                    <!-- Centre des moteurs (boulon) -->
                    <circle cx="10" cy="10" r="1.5" fill="rgba(0,0,0,0.8)"/>
                    <circle cx="50" cy="10" r="1.5" fill="rgba(0,0,0,0.8)"/>
                    <circle cx="10" cy="50" r="1.5" fill="rgba(0,0,0,0.8)"/>
                    <circle cx="50" cy="50" r="1.5" fill="rgba(0,0,0,0.8)"/>

                    <!-- LEDs de navigation (avant rouge, arrière vert) -->
                    <circle class="nav-led nav-led-front" cx="14" cy="6"  r="1.6" fill="#fb7185"/>
                    <circle class="nav-led nav-led-front" cx="46" cy="6"  r="1.6" fill="#fb7185"/>
                    <circle class="nav-led nav-led-back"  cx="14" cy="54" r="1.6" fill="#34d399"/>
                    <circle class="nav-led nav-led-back"  cx="46" cy="54" r="1.6" fill="#34d399"/>
                </svg>

                <!-- 4 HÉLICES animées (motion-blur via conic gradient + rotation) -->
                <div class="rotors-container">
                    <div class="rotor rotor-tl"></div>
                    <div class="rotor rotor-tr"></div>
                    <div class="rotor rotor-bl"></div>
                    <div class="rotor rotor-br"></div>
                </div>

                ${cargoIndicator}
            </div>`;
    }

    // ---- STATIONS ----
    function updateStationsOnMap(stations) {
        const seen = new Set();
        for (const [jid, info] of Object.entries(stations)) {
            seen.add(jid);
            const isBusy = info.occupied_by !== null && info.occupied_by !== undefined;
            const cls = isBusy ? 'busy' : 'free';
            const html = `
                <div class="station-marker ${cls}">
                    <div class="pulse"></div>
                    <div class="body">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round">
                            <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                        </svg>
                    </div>
                </div>`;
            const icon = L.divIcon({
                className: '',
                html,
                iconSize: [32, 32],
                iconAnchor: [16, 16],
            });
            if (!state.markers.stations[jid]) {
                state.markers.stations[jid] = L.marker([info.lat, info.lon], {
                    icon, zIndexOffset: 500,
                }).addTo(state.map).bindTooltip(jid.split('@')[0]);
            } else {
                state.markers.stations[jid].setIcon(icon);
            }
        }
        for (const jid in state.markers.stations) {
            if (!seen.has(jid)) {
                state.map.removeLayer(state.markers.stations[jid]);
                delete state.markers.stations[jid];
            }
        }
    }

    // ---- CUSTOMERS ----
    function updateCustomersOnMap(customers) {
        const seen = new Set();
        for (const [jid, info] of Object.entries(customers)) {
            seen.add(jid);
            const html = `
                <div class="customer-marker">
                    <div class="ping"></div>
                    <div class="body">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            <circle cx="12" cy="8" r="4"/>
                            <path d="M4 20c0-4 4-6 8-6s8 2 8 6"/>
                        </svg>
                    </div>
                </div>`;
            const icon = L.divIcon({
                className: '',
                html,
                iconSize: [26, 26],
                iconAnchor: [13, 13],
            });
            if (!state.markers.customers[jid]) {
                state.markers.customers[jid] = L.marker([info.lat, info.lon], {
                    icon, zIndexOffset: 200,
                }).addTo(state.map);
            } else {
                state.markers.customers[jid].setLatLng([info.lat, info.lon]);
            }
        }
        for (const jid in state.markers.customers) {
            if (!seen.has(jid)) {
                state.map.removeLayer(state.markers.customers[jid]);
                delete state.markers.customers[jid];
            }
        }
    }

    // ---- ORDERS (routes pickup→dropoff + markers) ----
    function updateOrdersOnMap(orders) {
        const seen = new Set();
        for (const [oid, order] of Object.entries(orders)) {
            if (order.status === 'completed' || order.status === 'failed') continue;
            seen.add(oid);

            const pickup = [order.pickup_lat, order.pickup_lon];
            const dropoff = [order.dropoff_lat, order.dropoff_lon];

            let layer = state.markers.routes[oid];
            if (!layer) {
                // Polyline route + 2 markers
                const route = L.polyline([pickup, dropoff], {
                    color: '#fbbf24',
                    weight: 2.5,
                    opacity: 0.7,
                    dashArray: '8 6',
                    className: 'leaflet-route',
                });
                const pIcon = L.divIcon({
                    className: '',
                    html: '<div class="pickup-marker"></div>',
                    iconSize: [20, 20],
                    iconAnchor: [10, 10],
                });
                const dIcon = L.divIcon({
                    className: '',
                    html: '<div class="dropoff-marker"></div>',
                    iconSize: [20, 20],
                    iconAnchor: [10, 10],
                });
                const pMarker = L.marker(pickup, { icon: pIcon, zIndexOffset: 100 })
                    .bindTooltip(`📦 Pickup ${oid}`);
                const dMarker = L.marker(dropoff, { icon: dIcon, zIndexOffset: 100 })
                    .bindTooltip(`🎯 Dropoff ${oid}`);

                const group = L.layerGroup([route, pMarker, dMarker]);
                group.addTo(state.map);
                state.markers.routes[oid] = group;
            }
        }
        for (const oid in state.markers.routes) {
            if (!seen.has(oid)) {
                state.map.removeLayer(state.markers.routes[oid]);
                delete state.markers.routes[oid];
            }
        }
    }

    // ---- FLEET PANEL (drones sidebar) ----
    function updateFleetPanel(drones) {
        const container = document.getElementById('fleet-list');
        const entries = Object.entries(drones);
        document.getElementById('fleet-count').textContent = entries.length;

        if (entries.length === 0) {
            container.innerHTML = `<div class="text-xs text-slate-500 text-center py-6">En attente des agents...</div>`;
            return;
        }

        const statusLabel = {
            idle: 'En attente',
            moving_to_pickup: 'Vers pickup',
            carrying: 'Livraison',
            moving_to_station: 'Vers station',
            charging: 'Recharge',
        };

        container.innerHTML = entries.map(([jid, info]) => {
            const status = info.status || 'idle';
            const battery = info.battery || 0;
            const profile = info.profile || {};
            const profileName = profile.name || jid.split('@')[0].toUpperCase();
            const profileIcon = profile.icon || '🚁';
            const profileType = profile.type || '';
            const batteryColor = battery < 25 ? '#fb7185'
                              : battery < 60 ? '#fbbf24'
                              : '#34d399';
            return `
                <div class="drone-card" data-status="${status}">
                    <div class="drone-header">
                        <span class="drone-name">
                            <span style="font-size:14px">${profileIcon}</span>
                            ${profileName}
                        </span>
                        <span class="drone-status ${status}">${statusLabel[status] || status}</span>
                    </div>
                    <div class="text-[9px] text-slate-500 italic mb-1 mt-0.5">
                        ${profileType}
                        ${profile.cargo_max_kg ? `· 📦 ${profile.cargo_max_kg}kg` : ''}
                        ${profile.speed_kmh ? `· ⚡ ${profile.speed_kmh}km/h` : ''}
                    </div>
                    <div class="flex items-center gap-2">
                        <div class="battery-bar flex-1">
                            <div class="battery-fill" style="width:${battery}%;background:${batteryColor};"></div>
                        </div>
                        <span class="battery-text">${battery.toFixed(1)}%</span>
                    </div>
                </div>`;
        }).join('');
    }

    // ---- FLEET PANEL (drones with profiles) ----
    function updateFleetWithProfiles(drones) {
        // Already handled in updateFleetPanel — but enrich with profile info
    }

    // ---- ORDERS PANEL ----
    function updateOrdersPanel(orders) {
        const container = document.getElementById('orders-list');
        const active = Object.entries(orders).filter(
            ([, o]) => o.status !== 'completed' && o.status !== 'failed'
        );
        document.getElementById('orders-count').textContent = active.length;

        if (active.length === 0) {
            container.innerHTML = `<div class="text-xs text-slate-500 text-center py-6">Aucune commande active.</div>`;
            return;
        }

        container.innerHTML = active.map(([oid, order]) => {
            const droneName = order.drone ? order.drone.split('@')[0] : '—';
            const statusBadge = order.status === 'assigned'
                ? `<span class="px-1.5 py-0.5 rounded text-[9px] bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">${droneName}</span>`
                : `<span class="px-1.5 py-0.5 rounded text-[9px] bg-amber-500/15 text-amber-300 border border-amber-500/30">pending</span>`;
            return `
                <div class="order-card">
                    <div class="flex justify-between items-center">
                        <span class="order-id">${oid}</span>
                        ${statusBadge}
                    </div>
                    <div class="order-route">
                        <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                        ${order.pickup[0]},${order.pickup[1]}
                        <span class="text-slate-600">→</span>
                        <span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                        ${order.dropoff[0]},${order.dropoff[1]}
                    </div>
                </div>`;
        }).join('');
    }

    // ---- EVENTS LOG ----
    let lastEventCount = 0;
    function updateEventsLog(events) {
        if (events.length === lastEventCount) return;
        lastEventCount = events.length;

        const container = document.getElementById('events-list');
        document.getElementById('events-counter').textContent = events.length;

        if (events.length === 0) {
            container.innerHTML = `<div class="text-slate-500 text-center py-6">En attente d'événements...</div>`;
            return;
        }

        // On affiche les 15 derniers (les plus récents en haut)
        const recent = events.slice(-15).reverse();
        container.innerHTML = recent.map(evt => `
            <div class="event-item">${escapeHtml(evt)}</div>
        `).join('');
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    // ---- CHARTS UPDATE ----
    let lastChartTick = 0;
    function updateCharts(stats) {
        // Donut success rate
        const delivered = stats.deliveries_completed;
        const failed = stats.deliveries_failed;
        state.charts.success.data.datasets[0].data = [delivered, failed];
        state.charts.success.update('none');

        // Performance line — push toutes les 1 seconde
        const now = Date.now();
        if (now - lastChartTick < 1000) return;
        lastChartTick = now;

        state.history.timestamps.push(new Date().toLocaleTimeString());
        state.history.delivered.push(delivered);
        state.history.active.push(stats.active_orders);

        // Garde les 30 derniers points
        if (state.history.timestamps.length > 30) {
            state.history.timestamps.shift();
            state.history.delivered.shift();
            state.history.active.shift();
        }

        state.charts.performance.data.labels = state.history.timestamps;
        state.charts.performance.data.datasets[0].data = state.history.delivered;
        state.charts.performance.data.datasets[1].data = state.history.active;
        state.charts.performance.update('none');
    }

    // =========================================================================
    // 7) FORMULAIRE "PASSER UNE COMMANDE"  (style Uber Eats)
    // =========================================================================

    const orderState = {
        pickup: null,           // [lat, lon]
        dropoff: null,          // [lat, lon]
        mode: null,             // null | 'pickup' | 'dropoff'
        pickupMarker: null,
        dropoffMarker: null,
    };

    async function initOrderForm() {
        // ---- Toggle collapse/expand du panneau ----
        const toggleBtn = document.getElementById('order-toggle');
        const panel = document.getElementById('order-panel');
        toggleBtn?.addEventListener('click', () => {
            panel.classList.toggle('collapsed');
        });

        // ---- Charger la liste des restaurants ----
        try {
            const res = await fetch('/api/restaurants');
            const data = await res.json();
            const select = document.getElementById('restaurant-select');
            data.restaurants.forEach(r => {
                const opt = document.createElement('option');
                opt.value = JSON.stringify({ lat: r.lat, lon: r.lon, name: r.name });
                opt.textContent = `${r.icon}  ${r.name} — ${r.cuisine}`;
                select.appendChild(opt);
            });

            // Sélection automatique au changement
            select.addEventListener('change', (e) => {
                if (!e.target.value) return;
                const { lat, lon, name } = JSON.parse(e.target.value);
                orderState.pickup = [lat, lon];
                if (orderState.pickupMarker) state.map.removeLayer(orderState.pickupMarker);
                orderState.pickupMarker = L.marker([lat, lon], {
                    icon: L.divIcon({
                        className: '',
                        html: '<div class="temp-marker pickup"></div>',
                        iconSize: [24, 24],
                        iconAnchor: [12, 12],
                    }),
                    zIndexOffset: 2000,
                }).addTo(state.map).bindPopup(`🍴 ${name}`);
                state.map.flyTo([lat, lon], 15);
                document.getElementById('pickup-label').textContent = name;
                document.getElementById('btn-set-pickup').classList.add('btn-confirmed-pickup');
                updateSendButton();
            });
        } catch (e) {
            console.warn('Restaurants KO', e);
        }

        // ---- Bouton "Définir pickup" ----
        document.getElementById('btn-set-pickup')?.addEventListener('click', () => {
            orderState.mode = 'pickup';
            document.getElementById('pickup-label').textContent = '👆 Clique sur la carte...';
            document.getElementById('map').classList.add('selecting-pickup');
            document.getElementById('map').classList.remove('selecting-dropoff');
        });

        // ---- Bouton "Définir dropoff" ----
        document.getElementById('btn-set-dropoff')?.addEventListener('click', () => {
            orderState.mode = 'dropoff';
            document.getElementById('dropoff-label').textContent = '👆 Clique sur la carte...';
            document.getElementById('map').classList.add('selecting-dropoff');
            document.getElementById('map').classList.remove('selecting-pickup');
        });

        // ---- Clic sur la carte pour positionner pickup ou dropoff ----
        state.map.on('click', (e) => {
            if (!orderState.mode) return;
            const { lat, lng } = e.latlng;

            if (orderState.mode === 'pickup') {
                orderState.pickup = [lat, lng];
                if (orderState.pickupMarker) state.map.removeLayer(orderState.pickupMarker);
                orderState.pickupMarker = L.marker([lat, lng], {
                    icon: L.divIcon({
                        className: '',
                        html: '<div class="temp-marker pickup"></div>',
                        iconSize: [24, 24],
                        iconAnchor: [12, 12],
                    }),
                    zIndexOffset: 2000,
                }).addTo(state.map).bindPopup('📦 Point de retrait');

                document.getElementById('pickup-label').textContent =
                    `Pickup : ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
                document.getElementById('btn-set-pickup').classList.add('btn-confirmed-pickup');
            } else if (orderState.mode === 'dropoff') {
                orderState.dropoff = [lat, lng];
                if (orderState.dropoffMarker) state.map.removeLayer(orderState.dropoffMarker);
                orderState.dropoffMarker = L.marker([lat, lng], {
                    icon: L.divIcon({
                        className: '',
                        html: '<div class="temp-marker dropoff"></div>',
                        iconSize: [24, 24],
                        iconAnchor: [12, 12],
                    }),
                    zIndexOffset: 2000,
                }).addTo(state.map).bindPopup('🎯 Point de livraison');

                document.getElementById('dropoff-label').textContent =
                    `Dropoff : ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
                document.getElementById('btn-set-dropoff').classList.add('btn-confirmed-dropoff');
            }

            orderState.mode = null;
            document.getElementById('map').classList.remove('selecting-pickup', 'selecting-dropoff');
            updateSendButton();
        });

        // ---- Bouton "Envoyer la commande" ----
        document.getElementById('btn-send-order')?.addEventListener('click', sendOrder);

        // ---- Etat initial du bouton "Envoyer" ----
        updateSendButton();
    }

    function updateSendButton() {
        const btn = document.getElementById('btn-send-order');
        if (!btn) return;
        btn.disabled = !(orderState.pickup && orderState.dropoff);
    }

    async function sendOrder() {
        if (!orderState.pickup || !orderState.dropoff) {
            showToast('Définis pickup et dropoff avant d\'envoyer', 'error');
            return;
        }

        const name = document.getElementById('order-name').value.trim() || 'Client Web';
        const desc = document.getElementById('order-desc').value.trim() || 'Colis';

        try {
            const res = await fetch('/api/order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    customer_name: name,
                    description: desc,
                    pickup_lat: orderState.pickup[0],
                    pickup_lon: orderState.pickup[1],
                    dropoff_lat: orderState.dropoff[0],
                    dropoff_lon: orderState.dropoff[1],
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            const droneName = data.closest_drone
                ? data.closest_drone.split('@')[0].toUpperCase()
                : '???';
            const dist = (data.distance_km ?? 0).toFixed(2);
            const etaReal = (data.estimated_time_min ?? 0).toFixed(1);
            const etaSim = (data.estimated_time_sim_s ?? 0).toFixed(0);
            const speedup = data.simulation_speedup ?? 15;

            showToast(
                `<div style="font-weight:600;color:#22d3ee;margin-bottom:6px">✅ Commande ${data.order_id}</div>` +
                `<div style="font-size:11px;line-height:1.7">` +
                `🚁 Drone assigné : <b style="color:#34d399">${droneName}</b><br>` +
                `📏 Distance : <b>${dist} km</b><br>` +
                `⏱️ ETA vie réelle : <b>${etaReal} min</b> (à 50 km/h)<br>` +
                `🎬 ETA simulation : <b>~${etaSim}s</b> (accéléré x${speedup})<br>` +
                `<span style="color:#94a3b8;font-style:italic;font-size:10px">` +
                `Le drone se déplace à sa vitesse réelle, accélérée x${speedup} pour la démo` +
                `</span>` +
                `</div>`,
                'success',
                7000
            );

            // Reset des markers temporaires
            if (orderState.pickupMarker) state.map.removeLayer(orderState.pickupMarker);
            if (orderState.dropoffMarker) state.map.removeLayer(orderState.dropoffMarker);
            orderState.pickup = null;
            orderState.dropoff = null;
            orderState.pickupMarker = null;
            orderState.dropoffMarker = null;
            document.getElementById('pickup-label').textContent = 'Ou clique sur la carte';
            document.getElementById('dropoff-label').textContent = 'Définir point de livraison';
            document.getElementById('btn-set-pickup').classList.remove('btn-confirmed-pickup');
            document.getElementById('btn-set-dropoff').classList.remove('btn-confirmed-dropoff');
            document.getElementById('restaurant-select').value = '';
            updateSendButton();
        } catch (e) {
            console.error(e);
            showToast(`❌ Erreur : ${e.message}`, 'error');
        }
    }

    // =========================================================================
    // 8) TOAST (notifications) — animations CSS + auto-dismiss
    // =========================================================================
    function showToast(message, type = 'info', duration = 4500) {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = message.replace(/\n/g, '<br>');
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'toast-slide-out 0.3s forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

})();

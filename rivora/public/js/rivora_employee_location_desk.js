/* Read-only Desk viewer. Every employee and route is scoped again by the server. */
frappe.provide('rivora');
rivora.LiveLocationDesk = class LiveLocationDesk {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = frappe.ui.make_app_page({parent: wrapper, title: __('Employee Live Location'), single_column: true});
        this.generation = 0;
        this.employees = [];
        this.fitted = false;
        const controls = $('<div class="row mb-3"></div>').appendTo(this.page.main);
        const control = (label, element) => {
            const column = $('<div class="col-sm-4 mb-2"></div>').appendTo(controls);
            $('<label></label>').text(__(label)).appendTo(column);
            return element.appendTo(column);
        };
        this.mode = control('View', $('<select class="form-control"></select>'));
        this.mode.append($('<option value="live"></option>').text(__('Live locations')));
        this.mode.append($('<option value="route"></option>').text(__('Route history')));
        this.employee = control('Employee', $('<select class="form-control"></select>'));
        this.employee.append($('<option value=""></option>').text(__('All permitted employees')));
        this.date = control('Date (UTC)', $('<input class="form-control" type="date">'));
        this.date.val(new Date().toISOString().slice(0, 10));
        this.date.attr('max', new Date().toISOString().slice(0, 10));
        this.date.attr('min', new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10));
        this.date.prop('disabled', true);
        this.note = $('<p class="text-muted"></p>').text(__('Recent means captured within three minutes. Grey locations are stale or stopped. Location sharing starts on the employee phone.')).appendTo(this.page.main);
        this.status = $('<p role="status"></p>').appendTo(this.page.main);
        this.mapArea = $('<div class="border rounded mb-3" style="height:440px;position:relative;z-index:1"></div>').appendTo(this.page.main);
        this.list = $('<div></div>').appendTo(this.page.main);
        this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');
        this.mode.on('change', () => { this.date.prop('disabled', this.mode.val() !== 'route'); this.fitted = false; this.refresh(); });
        this.employee.on('change', () => { this.fitted = false; this.refresh(); });
        this.date.on('change', () => { this.fitted = false; this.refresh(); });
        this.ready = this.makeMap();
        this.timer = setInterval(() => {
            if (this.visible() && this.mode.val() === 'live' && !this.loading) this.refresh();
        }, 30000);
    }
    visible() {
        const element = this.wrapper.jquery ? this.wrapper[0] : this.wrapper;
        return document.visibilityState === 'visible' && frappe.get_route()[0] === 'employee-location-tr' && element?.isConnected;
    }
    async makeMap() {
        try {
            await Promise.all([frappe.require('leaflet.bundle.js'), frappe.require('leaflet.bundle.css')]);
            this.map = L.map(this.mapArea[0]).setView([24.7, 46.7], 5);
            const configured = frappe.utils.map_defaults?.tiles?.default_tile;
            const url = configured?.url || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
            const options = configured?.options || {attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19};
            L.tileLayer(url, options).addTo(this.map);
            this.layers = L.featureGroup().addTo(this.map);
        } catch (error) {
            this.mapArea.text(__('Map could not load. Location details remain available below.'));
        }
    }
    async show() {
        await this.ready;
        this.map?.invalidateSize();
        await this.refresh();
    }
    request(method, args = {}) {
        return frappe.call({method: `rivora.live_location.${method}`, args, type: 'GET'}).then(response => response.message);
    }
    static hasPosition(point) {
        return typeof point.latitude === 'number' && typeof point.longitude === 'number' &&
            Number.isFinite(point.latitude) && Number.isFinite(point.longitude) &&
            Math.abs(point.latitude) <= 90 && Math.abs(point.longitude) <= 180;
    }
    roster(rows) {
        const selected = this.employee.val();
        this.employee.empty().append($('<option value=""></option>').text(__('All permitted employees')));
        for (const row of rows) this.employee.append($('<option></option>').val(row.employee).text(`${row.employee_name} (${row.employee}) - ${row.company}`));
        this.employee.val(rows.some(row => row.employee === selected) ? selected : '');
    }
    popup(row, label) {
        const element = document.createElement('div');
        element.textContent = `${label || row.employee_name || ''} ${row.employee || ''} - ${row.captured_at || ''} UTC - ${__('Accuracy')}: ${row.accuracy ?? '?'} m`;
        return element;
    }
    render(rows, route = false) {
        this.layers?.clearLayers();
        this.list.empty();
        const valid = rows.filter(rivora.LiveLocationDesk.hasPosition);
        if (route && this.map && valid.length > 1) {
            L.polyline(valid.map(row => [row.latitude, row.longitude]), {color: '#008577', weight: 3}).addTo(this.layers);
        }
        rows.forEach((row, index) => {
            const entry = $('<div class="border-bottom p-2"></div>').appendTo(this.list);
            $('<strong></strong>').text(route ? `${row.captured_at} UTC` : `${row.employee_name} (${row.employee})`).appendTo(entry);
            $('<div class="text-muted"></div>').text(route ? `${row.latitude}, ${row.longitude} - ${__('Accuracy')}: ${row.accuracy} m` : `${row.company} - ${__(row.status)}${row.captured_at ? ' - '+row.captured_at+' UTC - '+__('Accuracy')+': '+row.accuracy+' m' : ''}`).appendTo(entry);
            if (this.map && rivora.LiveLocationDesk.hasPosition(row) && (!route || index === 0 || index === rows.length - 1)) {
                const marker = L.circleMarker([row.latitude, row.longitude], {radius: 7, color: route || row.status === 'recent' ? '#008577' : '#777', fillOpacity: .8});
                marker.bindPopup(this.popup(row, route ? index === 0 ? __('Start') : __('End') : null)).addTo(this.layers);
            }
        });
        if (this.map && valid.length && !this.fitted) {
            this.map.fitBounds(this.layers.getBounds(), {padding: [24, 24], maxZoom: 16});
            this.fitted = true;
        }
        if (!rows.length) this.list.text(__('No captured locations are available for this selection.'));
    }
    async refresh() {
        const generation = ++this.generation;
        this.loading = true;
        this.status.text(__('Loading locations...'));
        try {
            await this.ready;
            const latest = await this.request('latest');
            if (generation !== this.generation) return;
            this.employees = latest.employees || [];
            this.roster(this.employees);
            const selected = this.employee.val();
            if (this.mode.val() === 'route') {
                if (!selected) { this.render([]); this.status.text(__('Select an employee to view route history.')); return; }
                const route = await this.request('route', {employee_id: selected, date: this.date.val()});
                if (generation !== this.generation) return;
                this.render(route.points || [], true);
                this.status.text(`${route.date} UTC - ${(route.points || []).length} ${__('captured points')}${route.truncated ? ' - '+__('First 2,000 points only') : ''}. ${__('Lines connect samples; they are not road directions.')}`);
            } else {
                this.render(this.employees.filter(row => !selected || row.employee === selected));
                this.status.text(`${__('Last refreshed')}: ${new Date().toLocaleTimeString()}`);
            }
        } catch (error) {
            if (generation === this.generation) {
                this.render([]);
                this.status.text(__('Locations could not load. Check Employee permissions and Enable Employee Live Location in Rivora Mobile Settings.'));
            }
        } finally { if (generation === this.generation) this.loading = false; }
    }
};

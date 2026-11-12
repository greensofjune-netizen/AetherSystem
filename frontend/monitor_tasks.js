(() => {
    const form = document.getElementById('task-form');
    const fields = document.getElementById('task-fields');
    const title = document.getElementById('task-title');
    const save = document.getElementById('task-save');
    const refresh = document.getElementById('task-refresh');
    const list = document.getElementById('task-list');
    const connection = document.getElementById('task-connection');
    const notice = document.getElementById('task-notice');
    const error = document.getElementById('task-error');
    let loading = null;
    let saving = false;

    async function requestTasks(options = {}) {
        const response = await fetch('/api/v1/tasks', {
            ...options,
            cache: 'no-store',
            signal: AbortSignal.timeout(5000),
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(typeof result.detail === 'string'
                ? result.detail : `Task request failed (HTTP ${response.status}).`);
        }
        return result;
    }

    function renderTasks(tasks) {
        const rows = tasks.map((task) => {
            const row = document.createElement('li');
            row.dataset.taskId = String(task.id);
            row.textContent = `#${task.id} ${task.title} - ${task.status}`;
            return row;
        });
        list.replaceChildren(...rows);
        connection.textContent = `Task backend connected. ${tasks.length} task(s).`;
    }

    function loadTasks() {
        if (saving) return Promise.resolve();
        if (loading) return loading;
        refresh.disabled = true;
        loading = requestTasks().then(renderTasks).catch((failure) => {
            connection.textContent = `Task backend unavailable. Displayed tasks may be stale. ${failure.message}`;
        }).finally(() => {
            loading = null;
            refresh.disabled = false;
        });
        return loading;
    }

    fields.disabled = false;
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (saving) return;
        saving = true;
        fields.disabled = true;
        save.textContent = 'Saving...';
        notice.textContent = '';
        error.textContent = '';
        try {
            // Finish any older read before saving so it cannot overwrite
            // the list refresh following an acknowledged write.
            if (loading) await loading;
            const task = await requestTasks({
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: title.value }),
            });
            form.reset();
            notice.textContent = `Saved task #${task.id}.`;
        } catch (failure) {
            error.textContent = `Save not confirmed: ${failure.message} Your draft is retained. Refresh tasks before retrying; the request may have been saved.`;
        } finally {
            saving = false;
            fields.disabled = false;
            save.textContent = 'Add task';
        }
        await loadTasks();
    });
    refresh.addEventListener('click', loadTasks);
    async function poll() {
        await loadTasks();
        setTimeout(poll, 5000);
    }
    poll();
})();

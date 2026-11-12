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

    async function requestTasks(options = {}, path = '/api/v1/tasks') {
        const response = await fetch(path, {
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
        const focusedId = document.activeElement.closest?.('[data-task-id]')?.dataset.taskId;
        const rows = tasks.map((task) => {
            const row = document.createElement('li');
            row.dataset.taskId = String(task.id);
            row.textContent = `#${task.id} ${task.title} - ${task.status}`;
            const action = document.createElement('button');
            action.type = 'button';
            const operation = task.status === 'done' ? 'reopen' : 'complete';
            action.textContent = `${operation === 'complete' ? 'Complete' : 'Reopen'} task #${task.id}`;
            action.disabled = saving;
            action.addEventListener('click', () => updateStatus(task.id, operation));
            row.append(action);
            return row;
        });
        list.replaceChildren(...rows);
        if (focusedId) list.querySelector(`[data-task-id="${focusedId}"] button`)?.focus();
        connection.textContent = `Task backend connected. ${tasks.length} task(s).`;
    }

    function setSaving(value) {
        saving = value;
        fields.disabled = value;
        list.querySelectorAll('button').forEach((button) => { button.disabled = value; });
    }

    async function updateStatus(taskId, operation) {
        if (saving) return;
        const restoreFocus = list.contains(document.activeElement);
        setSaving(true);
        notice.textContent = '';
        error.textContent = '';
        try {
            if (loading) await loading;
            const task = await requestTasks(
                { method: 'POST' }, `/api/v1/tasks/${taskId}/${operation}`
            );
            notice.textContent = `Task #${task.id} ${task.status === 'done' ? 'completed' : 'reopened'}.`;
        } catch (failure) {
            error.textContent = `Update not confirmed: ${failure.message} Displayed status may be stale. Refresh tasks before retrying; the update may have been saved.`;
        } finally {
            setSaving(false);
        }
        await loadTasks();
        if (restoreFocus && (document.activeElement === document.body || list.contains(document.activeElement))) {
            list.querySelector(`[data-task-id="${taskId}"] button`)?.focus();
        }
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
        setSaving(true);
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
            setSaving(false);
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

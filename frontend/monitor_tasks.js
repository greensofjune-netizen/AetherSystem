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
    const filters = document.getElementById('task-filters');
    const filterFields = document.getElementById('task-filter-fields');
    const empty = document.getElementById('task-empty');
    const editor = document.getElementById('task-editor');
    const editFields = document.getElementById('task-edit-fields');
    const editTitle = document.getElementById('task-edit-title');
    const editDescription = document.getElementById('task-edit-description');
    const editDue = document.getElementById('task-edit-due');
    const editSave = document.getElementById('task-edit-save');
    let loading = null;
    let saving = false;
    let editing = null;
    let viewPath = '/api/v1/tasks';
    let viewLabel = 'All tasks';

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
        const focused = document.activeElement;
        const focusedId = focused.closest?.('[data-task-id]')?.dataset.taskId;
        const focusedAction = focused.dataset.taskAction;
        const rows = tasks.map((task) => {
            const row = document.createElement('li');
            row.dataset.taskId = String(task.id);
            row.textContent = `#${task.id} ${task.title} - ${task.status}`;
            const action = document.createElement('button');
            action.type = 'button';
            action.dataset.taskAction = 'status';
            const operation = task.status === 'done' ? 'reopen' : 'complete';
            action.textContent = `${operation === 'complete' ? 'Complete' : 'Reopen'} task #${task.id}`;
            action.disabled = saving;
            action.addEventListener('click', () => updateStatus(task.id, operation));
            row.append(action);
            const description = document.createElement('p');
            description.className = 'task-description';
            description.textContent = task.description || 'No description.';
            const metadata = document.createElement('p');
            metadata.textContent = `Priority: ${task.priority}. Due date: ${task.due_date || 'None'}.`;
            const edit = document.createElement('button');
            edit.type = 'button';
            edit.dataset.taskAction = 'edit';
            edit.textContent = `Edit task #${task.id}`;
            edit.disabled = saving || editing !== null;
            edit.setAttribute('aria-controls', 'task-editor');
            edit.addEventListener('click', () => openEditor(task));
            row.append(description, metadata, edit);
            return row;
        });
        list.replaceChildren(...rows);
        if (focusedId) {
            (list.querySelector(`[data-task-id="${focusedId}"] [data-task-action="${focusedAction}"]`) || refresh).focus();
        }
        empty.textContent = viewPath === '/api/v1/tasks'
            ? 'No tasks yet. Add a task to get started.'
            : 'No tasks match the applied filters.';
        empty.hidden = tasks.length !== 0;
        connection.textContent = `Task backend connected. ${tasks.length} task(s). View: ${viewLabel}.`;
    }

    function setSaving(value) {
        saving = value;
        fields.disabled = value;
        filterFields.disabled = value;
        editFields.disabled = value || editing === null;
        list.querySelectorAll('button').forEach((button) => {
            button.disabled = value || (button.dataset.taskAction === 'edit' && editing !== null);
        });
    }

    function openEditor(task) {
        if (saving || editing) return;
        editing = task;
        editTitle.value = task.title;
        editDescription.value = task.description;
        editDue.value = task.due_date || '';
        editor.querySelector(`input[name="priority"][value="${task.priority}"]`).checked = true;
        document.getElementById('task-edit-heading').textContent = `Edit task #${task.id}`;
        editor.hidden = false;
        setSaving(false);
        editTitle.focus();
    }

    function closeEditor() {
        const taskId = editing.id;
        editing = null;
        editor.hidden = true;
        editor.reset();
        setSaving(false);
        return taskId;
    }

    function focusEdit(taskId) {
        (list.querySelector(`[data-task-id="${taskId}"] [data-task-action="edit"]`) || refresh).focus();
    }

    document.getElementById('task-edit-cancel').addEventListener('click', () => {
        if (saving || !editing) return;
        focusEdit(closeEditor());
    });

    editor.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (saving || !editing) return;
        const changes = {};
        const values = {
            title: editTitle.value,
            description: editDescription.value,
            priority: editor.querySelector('input[name="priority"]:checked').value,
        };
        for (const [key, value] of Object.entries(values)) {
            if (value !== editing[key]) changes[key] = value;
        }
        if (editDue.value !== (editing.due_date || '')) {
            if (editDue.value) changes.due_date = editDue.value;
            else changes.clear_due_date = true;
        }
        notice.textContent = '';
        error.textContent = '';
        if (!Object.keys(changes).length) {
            notice.textContent = 'No changes to save.';
            return;
        }
        setSaving(true);
        editSave.textContent = 'Saving changes...';
        let savedId = null;
        try {
            if (loading) await loading;
            const task = await requestTasks({
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(changes),
            }, `/api/v1/tasks/${editing.id}`);
            notice.textContent = `Saved changes to task #${task.id}.`;
            savedId = closeEditor();
        } catch (failure) {
            error.textContent = `Edit not confirmed: ${failure.message} Your edit draft is retained. Compare the refreshed list before retrying; the edit may have been saved.`;
        } finally {
            setSaving(false);
            editSave.textContent = 'Save changes';
        }
        await loadTasks();
        if (savedId !== null && (document.activeElement === document.body || editor.contains(document.activeElement))) {
            focusEdit(savedId);
        }
    });

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
            (list.querySelector(`[data-task-id="${taskId}"] button`) || refresh).focus();
        }
    }

    function loadTasks() {
        if (saving) return Promise.resolve();
        if (loading) return loading.then(() => loadTasks());
        const path = viewPath;
        refresh.disabled = true;
        loading = requestTasks({}, path).then((tasks) => {
            if (path === viewPath) renderTasks(tasks);
        }).catch((failure) => {
            if (path !== viewPath) return;
            empty.hidden = true;
            connection.textContent = `Task backend unavailable. Displayed tasks may be stale or from the previous view. Requested view: ${viewLabel}. ${failure.message}`;
        }).finally(() => {
            loading = null;
            refresh.disabled = false;
        });
        return loading;
    }

    fields.disabled = false;
    filterFields.disabled = false;
    filters.addEventListener('submit', (event) => {
        event.preventDefault();
        if (saving) return;
        const selected = filters.querySelector('input[name="status"]:checked');
        const search = document.getElementById('task-search').value.trim();
        const query = new URLSearchParams();
        if (selected.value) query.set('status', selected.value);
        if (search) query.set('search', search);
        viewPath = `/api/v1/tasks${query.size ? `?${query}` : ''}`;
        viewLabel = `${selected.value || 'All'} tasks${search ? ` matching "${search}"` : ''}`;
        empty.hidden = true;
        connection.textContent = `Loading tasks. Displayed tasks may be from the previous view. Requested view: ${viewLabel}.`;
        loadTasks();
    });
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

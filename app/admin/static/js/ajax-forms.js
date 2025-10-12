/**
 * Universal AJAX form handler for admin panel
 * Converts all form submissions to AJAX calls with toast notifications
 */

document.addEventListener('DOMContentLoaded', function() {
  // Handle all forms with data-ajax="true" attribute
  document.querySelectorAll('form[data-ajax="true"]').forEach(form => {
    form.addEventListener('submit', async function(e) {
      e.preventDefault();

      const formData = new FormData(form);
      const action = form.action;
      const method = form.method || 'POST';

      // Get confirmation message if specified
      const confirmMsg = form.dataset.confirm;
      if (confirmMsg && !confirm(confirmMsg)) {
        return;
      }

      try {
        const response = await fetch(action, {
          method: method,
          body: formData
        });

        const result = await response.json();

        if (result.success) {
          // Show success notification
          if (window.showNotification) {
            window.showNotification(result.message || 'Операция выполнена успешно', 'success');
          } else {
            alert(result.message || 'Операция выполнена успешно');
          }

          // Handle post-success actions
          const onSuccess = form.dataset.onSuccess;
          if (onSuccess === 'reload') {
            setTimeout(() => window.location.reload(), 1000);
          } else if (onSuccess === 'redirect' && result.redirect) {
            setTimeout(() => window.location.href = result.redirect, 1000);
          } else if (onSuccess === 'remove-row') {
            // Remove parent row/card element
            const row = form.closest('tr') || form.closest('.card') || form.closest('[data-item-row]');
            if (row) {
              row.style.transition = 'opacity 0.3s';
              row.style.opacity = '0';
              setTimeout(() => row.remove(), 300);
            }
          }
        } else {
          // Show error notification
          if (window.showNotification) {
            window.showNotification(result.error || 'Произошла ошибка', 'error');
          } else {
            alert(result.error || 'Произошла ошибка');
          }
        }
      } catch (error) {
        console.error('AJAX form error:', error);
        if (window.showNotification) {
          window.showNotification('Ошибка сети: ' + error.message, 'error');
        } else {
          alert('Ошибка сети: ' + error.message);
        }
      }
    });
  });

  // Handle all buttons with data-ajax-action attribute
  document.querySelectorAll('[data-ajax-action]').forEach(button => {
    button.addEventListener('click', async function(e) {
      e.preventDefault();

      const action = button.dataset.ajaxAction;
      const method = button.dataset.ajaxMethod || 'POST';
      const confirmMsg = button.dataset.confirm;

      if (confirmMsg && !confirm(confirmMsg)) {
        return;
      }

      // Get CSRF token
      const csrfInput = document.querySelector('input[name="csrf"]');
      const csrf = csrfInput ? csrfInput.value : '';

      try {
        const formData = new FormData();
        formData.append('csrf', csrf);

        // Add any additional data attributes
        Object.keys(button.dataset).forEach(key => {
          if (key.startsWith('param')) {
            const paramName = key.replace('param', '').toLowerCase();
            formData.append(paramName, button.dataset[key]);
          }
        });

        const response = await fetch(action, {
          method: method,
          body: formData
        });

        const result = await response.json();

        if (result.success) {
          if (window.showNotification) {
            window.showNotification(result.message || 'Операция выполнена успешно', 'success');
          } else {
            alert(result.message || 'Операция выполнена успешно');
          }

          // Handle post-success actions
          const onSuccess = button.dataset.onSuccess;
          if (onSuccess === 'reload') {
            setTimeout(() => window.location.reload(), 1000);
          } else if (onSuccess === 'redirect' && result.redirect) {
            setTimeout(() => window.location.href = result.redirect, 1000);
          } else if (onSuccess === 'remove-row') {
            const row = button.closest('tr') || button.closest('.card') || button.closest('[data-item-row]');
            if (row) {
              row.style.transition = 'opacity 0.3s';
              row.style.opacity = '0';
              setTimeout(() => row.remove(), 300);
            }
          } else if (onSuccess === 'update-status') {
            // Update status badge or similar
            const statusEl = button.closest('[data-status]');
            if (statusEl && result.status) {
              statusEl.dataset.status = result.status;
              statusEl.textContent = result.status;
            }
          }
        } else {
          if (window.showNotification) {
            window.showNotification(result.error || 'Произошла ошибка', 'error');
          } else {
            alert(result.error || 'Произошла ошибка');
          }
        }
      } catch (error) {
        console.error('AJAX button action error:', error);
        if (window.showNotification) {
          window.showNotification('Ошибка сети: ' + error.message, 'error');
        } else {
          alert('Ошибка сети: ' + error.message);
        }
      }
    });
  });
});

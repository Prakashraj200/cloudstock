document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alertBox = document.getElementById('alertBox');
    const loadingDiv = document.querySelector('.loading');
    loadingDiv.style.display = 'block';
    try {
        const r = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                email: document.getElementById('email').value,
                password: document.getElementById('password').value
            })
        });
        const d = await r.json();
        loadingDiv.style.display = 'none';
        if (r.ok) {
            alertBox.textContent = 'Success!';
            alertBox.className = 'alert success';
            alertBox.style.display = 'block';
            setTimeout(() => window.location.href = d.user_type === 'owner' ? '/owner-dashboard' : '/supplier-dashboard', 1000);
        } else {
            alertBox.textContent = d.error;
            alertBox.className = 'alert error';
            alertBox.style.display = 'block';
        }
    } catch (error) {
        loadingDiv.style.display = 'none';
        alertBox.textContent = 'Error';
        alertBox.className = 'alert error';
        alertBox.style.display = 'block';
    }
});
function selectUserType(type) {
    document.querySelectorAll('.user-type-card').forEach(c => c.classList.remove('selected'));
    event.currentTarget.classList.add('selected');
    document.querySelector(`input[value="${type}"]`).checked = true;
}
document.getElementById('registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const userType = document.querySelector('input[name="user_type"]:checked');
    const alertBox = document.getElementById('alertBox');
    if (!userType) {
        alertBox.textContent = 'Select user type';
        alertBox.className = 'alert error';
        alertBox.style.display = 'block';
        return;
    }
    document.querySelector('.loading').style.display = 'block';
    try {
        const r = await fetch('/api/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: document.getElementById('name').value,
                email: document.getElementById('email').value,
                password: document.getElementById('password').value,
                user_type: userType.value,
                company_name: document.getElementById('companyName').value
            })
        });
        const d = await r.json();
        document.querySelector('.loading').style.display = 'none';
        if (r.ok) {
            alertBox.textContent = 'Success! Redirecting...';
            alertBox.className = 'alert success';
            alertBox.style.display = 'block';
            setTimeout(() => window.location.href = '/login', 2000);
        } else {
            alertBox.textContent = d.error;
            alertBox.className = 'alert error';
            alertBox.style.display = 'block';
        }
    } catch (error) {
        document.querySelector('.loading').style.display = 'none';
    }
});
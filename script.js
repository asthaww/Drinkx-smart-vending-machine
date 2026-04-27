document.addEventListener("DOMContentLoaded", () => {
    const state = {
        products: {}, addons: {}, selectedBase: "water",
        selectedSizeId: null, selectedFlavor: "chocolate", selectedAddons: [],
        totalPrice: 0, currentSystemState: "idle", pollInterval: null, proteinChart: null
    };

    const screens = {
        selection: document.getElementById("selection-screen"),
        dispensing: document.getElementById("dispensing-screen"),
        complete: document.getElementById("complete-screen"),
        dashboard: document.getElementById("dashboard-screen")
    };
    
    const els = {
        base: document.getElementById("base-options"),
        size: document.getElementById("size-options"),
        flavor: document.getElementById("flavor-options"),
        addon: document.getElementById("addon-options"),
        price: document.getElementById("total-price"),
        payBtn: document.getElementById("pay-button"),
        shakeName: document.getElementById("shake-name")
    };

    function showScreen(id) {
        Object.values(screens).forEach(s => s.classList.remove("active"));
        if(screens[id]) screens[id].classList.add("active");
        if(id === 'dashboard') renderChart();
    }

    function formatPrice(p) { 
        return (p/100).toLocaleString("en-IN", {style:"currency", currency:"INR"}); 
    }

    async function loadData() {
        const [prodRes, addonRes] = await Promise.all([
            fetch('/api/products'), fetch('/api/addons')
        ]);
        state.products = await prodRes.json();
        state.addons = await addonRes.json();
        
        // Render Sizes
        els.size.innerHTML = "";
        Object.entries(state.products).forEach(([id, p]) => {
            const l = document.createElement("label");
            l.className = "option-card";
            l.innerHTML = `<input type="radio" name="size" value="${id}">
                           <span>${p.name}<span class="price">${formatPrice(p.price)}</span></span>`;
            els.size.appendChild(l);
        });

        // Render Addons
        els.addon.innerHTML = "";
        Object.entries(state.addons).forEach(([id, a]) => {
            const l = document.createElement("label");
            l.className = "option-card";
            l.innerHTML = `<input type="checkbox" name="addon" value="${id}">
                           <span>${a.name}<span class="price">+ ${formatPrice(a.price)}</span></span>`;
            els.addon.appendChild(l);
        });
    }

    function updatePrice() {
        let total = 0;
        if(state.selectedBase === 'milk') total += 1000;
        if(state.selectedSizeId) total += state.products[state.selectedSizeId].price;
        else {
            els.price.textContent = formatPrice(0);
            els.payBtn.textContent = "Select a Size";
            els.payBtn.disabled = true;
            return;
        }
        state.selectedAddons.forEach(id => total += state.addons[id].price);
        state.totalPrice = total;
        els.price.textContent = formatPrice(total);
        els.payBtn.textContent = `Pay ${formatPrice(total)}`;
        els.payBtn.disabled = false;
    }

    // --- RAZORPAY PAYMENT FLOW ---
    async function startPayment() {
        els.payBtn.disabled = true;
        els.payBtn.textContent = "Processing...";

        try {
            // 1. Create Order (Always ₹1.00 for testing)
            const orderRes = await fetch('/api/create-order', {method: 'POST'});
            const orderData = await orderRes.json();

            // 2. Open Razorpay Options
            const options = {
                "key": orderData.key_id,
                "amount": orderData.amount,
                "currency": "INR",
                "name": "DrinkX",
                "description": "Protein Shake Payment",
                "order_id": orderData.order_id,
                "handler": async function (response) {
                    // 3. Verify Payment
                    verifyPayment(response);
                },
                "prefill": { "contact": "9999999999", "email": "test@drinkx.in" },
                "theme": { "color": "#ec4899" },
                "modal": { "ondismiss": function() {
                    els.payBtn.disabled = false;
                    updatePrice();
                }}
            };
            const rzp1 = new Razorpay(options);
            rzp1.open();

        } catch (e) {
            console.error(e);
            alert("Payment init failed");
            els.payBtn.disabled = false;
        }
    }

    async function verifyPayment(paymentResponse) {
        try {
            const res = await fetch('/api/verify-payment', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    ...paymentResponse,
                    product_id: state.selectedSizeId,
                    real_value: state.totalPrice // Send real cart value for stats
                })
            });
            
            if(res.ok) {
                // Payment Success!
                els.shakeName.textContent = state.products[state.selectedSizeId].name;
                showScreen('dispensing');
                pollState();
            } else {
                alert("Payment Verification Failed");
                els.payBtn.disabled = false;
            }
        } catch(e) {
            console.error(e);
        }
    }

    // --- POLLING & UI LOGIC ---
    function pollState() {
        if(state.pollInterval) clearInterval(state.pollInterval);
        state.pollInterval = setInterval(async () => {
            const res = await fetch('/api/system-state');
            const data = await res.json();
            
            if(state.currentSystemState === 'post_payment' && data.state === 'idle') {
                clearInterval(state.pollInterval);
                showScreen('complete');
                setTimeout(() => { resetUI(); showScreen('selection'); }, 8000);
            }
            state.currentSystemState = data.state;
        }, 1500);
    }

    function resetUI() {
        state.selectedBase = "water";
        state.selectedSizeId = null;
        state.selectedFlavor = "chocolate";
        state.selectedAddons = [];
        
        document.querySelectorAll('input').forEach(i => i.checked = false);
        document.querySelector('input[value="water"]').checked = true;
        document.querySelector('input[value="chocolate"]').checked = true;
        
        updateCards(els.base); updateCards(els.size);
        updateCards(els.flavor); updateCards(els.addon);
        updatePrice();
    }

    function updateCards(container) {
        container.querySelectorAll('.option-card').forEach(c => {
            c.classList.toggle('selected', c.querySelector('input').checked);
        });
    }

    function renderChart() {
        if(state.proteinChart) state.proteinChart.destroy();
        const ctx = document.getElementById('protein-chart').getContext('2d');
        state.proteinChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
                datasets: [{
                    label: 'Protein (g)',
                    data: [0, 30, 30, 0, 60, 0, 0],
                    backgroundColor: 'rgba(236, 72, 153, 0.7)',
                    borderRadius: 5
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: {display: false} },
                scales: { y: { beginAtZero: true, grid: {color: 'rgba(255,255,255,0.1)'} } }
            }
        });
    }

    // Events
    els.base.addEventListener('change', e => { state.selectedBase = e.target.value; updateCards(els.base); updatePrice(); });
    els.size.addEventListener('change', e => { state.selectedSizeId = e.target.value; updateCards(els.size); updatePrice(); });
    els.flavor.addEventListener('change', e => { state.selectedFlavor = e.target.value; updateCards(els.flavor); });
    els.addon.addEventListener('change', e => {
        state.selectedAddons = [...els.addon.querySelectorAll('input:checked')].map(i => i.value);
        updateCards(els.addon); updatePrice();
    });
    
    els.payBtn.addEventListener('click', startPayment);
    document.getElementById('dashboard-button').addEventListener('click', () => showScreen('dashboard'));
    document.getElementById('dashboard-close-button').addEventListener('click', () => showScreen('selection'));

    loadData();
});
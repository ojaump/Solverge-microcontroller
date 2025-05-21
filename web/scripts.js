function toggleMenu() {
  const menu = document.getElementById('menu');
  menu.classList.toggle('hidden');
}

function scanNetworks() {
  fetch('/scan')
    .then((res) => res.json())
    .then((networks) => {
      const list = document.getElementById('networkList');
      list.innerHTML = '';
      networks.forEach((net) => {
        const div = document.createElement('div');
        div.className = 'network-item';
        div.innerHTML = `
          <span>${net.ssid}</span>
          <span style="color: ${getSignalColor(net.rssi)}">📶</span>
          <button onclick="selectSSID('${net.ssid}')">Conectar</button>
        `;
        list.appendChild(div);
      });
      document.getElementById('networksModal').classList.remove('hidden');
    })
    .catch(() => alert('Erro ao buscar redes.'));
}

function closeModal() {
  document.getElementById('networksModal').classList.add('hidden');
}

function selectSSID(ssid) {
  document.getElementById('ssid').value = ssid;
  closeModal();
}

function getSignalColor(rssi) {
  if (rssi === null) return "color: gray";

  const level = parseInt(rssi);
  if (level < -80) return "color: red";
  if (level < -65) return "color: orange";
  if (level < -50) return "color: gold";
  return "color: green";
}

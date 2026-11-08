# PMO Guard

Windows Service (bukan ekstensi) yang memantau ketikan di browser dan memblokir akses ke situs/kata terlarang.

## Arsitektur
```
PMOGuard service (SYSTEM, auto-start, auto-restart)
 ├─ meluncurkan & menjaga agent di sesi user (relaunch bila di-kill / logon baru)
 └─ menjaga blok hosts file untuk block_domains
agent.py (sesi user)
 ├─ keyboard hook WH_KEYBOARD_LL, hanya aktif saat browser jadi window foreground
 ├─ buffer 80 karakter di RAM (tidak pernah ditulis ke disk / dikirim)
 ├─ lapis 2: cek judul window browser tiap 1 detik (menangkap klik link / URL paste)
 └─ saat match: Ctrl+W (tutup tab) + pesan; 3x dalam 10 menit -> kunci PC
```
Alasan dua proses: service berjalan di Session 0 dan tidak bisa hook keyboard user.

## Install
```
pip install pywin32
python install.py install      # Command Prompt as Administrator
```
- Daftar blokir: `C:\Program Files\PMOGuard\config.json` (hanya admin yang bisa edit; agent reload otomatis, hosts disinkron tiap 60 dtk).
- Log kejadian: `C:\ProgramData\PMOGuard\events.log` (hanya sumber + rule, bukan teks ketikan).
- Hapus: `python install.py uninstall`

## Config
- `block_words`: cocok per kata utuh (aman untuk kata pendek).
- `block_contains`: cocok sebagai substring.
- `block_domains`: diblokir di hosts file + dipantau saat diketik.
- `action`: `close_tab` atau `alert_only`.
- `check_title`: false bila terlalu banyak false positive.

## Batasan (jujur)
- Siapa pun yang punya hak admin bisa stop/uninstall. Agar benar-benar efektif: pakai akun Windows **Standard** untuk harian, dan minta partner akuntabilitas memegang password admin.
- Kata di config juga memicu saat mengetik di tempat lain di browser (mis. Google Docs). Atur daftar sesuai kebutuhan.
- Browser lain/portable (nama exe tak ada di `browsers`), aplikasi non-browser, dan HP tidak tercakup. Tambahkan DNS filter (mis. CleanBrowsing/Cloudflare Family) di router untuk lapis tambahan.
- Paste (Ctrl+V) tidak terbaca ketikannya; tertangkap lewat lapis judul window setelah halaman termuat.
- Hanya pasang di PC milik sendiri atau dengan persetujuan pemiliknya.

## Pasang lewat NSSM
```
pip install pywin32
python install.py install-nssm     # Administrator; nssm.exe harus ada di PATH
python install.py uninstall-nssm
```
NSSM menjalankan `launcher.py` (watchdog) sebagai service SYSTEM; launcher yang meluncurkan `agent.py` ke sesi user. Log launcher: `C:\ProgramData\PMOGuard\events.log`.

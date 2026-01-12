# wawi

## Installation

sudo apt update
sudo apt install \
    python3-gi \
    gir1.2-gtk-3.0 \
    gir1.2-webkit2-4.1

python -m venv --site-system-packages ~/wawienv
source ~/venv/bin/activate

pip install -r requirements.txt

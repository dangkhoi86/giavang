import requests
from bs4 import BeautifulSoup

url = "https://webgia.com/gia-vang/mi-hong/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

response = requests.get(url, headers=headers)
response.raise_for_status()  # Báo lỗi nếu không truy cập được

soup = BeautifulSoup(response.text, "html.parser")

# Tìm bảng giá vàng
table = soup.find("table", class_="table table-radius table-hover")
rows = table.find_all("tr")

lines = []
for row in rows[1:]:  # Bỏ qua header
    cols = row.find_all(["th", "td"])
    if len(cols) >= 3:
        gold_type = cols[0].get_text(strip=True)
        buy_price = cols[1].get_text(strip=True)
        sell_price = cols[2].get_text(strip=True)
        line = f"{gold_type}: {buy_price} - {sell_price}"
        print(line)
        lines.append(line)

# Ghi ra file txt
with open("gold_price.txt", "w", encoding="utf-8") as f:
    for line in lines:
        f.write(line + "\n")

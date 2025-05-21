import os
import json
import requests
from bs4 import BeautifulSoup
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_webgia_gold_prices():
    url = "https://giavang.org/trong-nuoc/mi-hong/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        gold_map = {}
        # Lấy thời gian cập nhật
        # Lấy thời gian cập nhật
        update_time = ""
        h1 = soup.find("h1", class_="box-headline highlight")
        logging.info(f"Nội dung thẻ h1: {h1}")
        if h1:
            small = h1.find("small")
            logging.info(f"Nội dung thẻ small: {small}")
            if small:
                update_time = small.get_text(strip=True)
        if not update_time:
            # Thử lấy tất cả thẻ small
            for small in soup.find_all("small"):
                logging.info(f"Thẻ small: {small.get_text(strip=True)}")
        if update_time:
            logging.info(f"Thời gian cập nhật lấy được: {update_time}")
        else:
            logging.warning("Không lấy được thời gian cập nhật từ trang web!")
        # Lấy giá vàng
        for tr in soup.find_all("tr"):
            th = tr.find("th")
            tds = tr.find_all("td", class_="text-right")
            if th and tds:
                gold_type = th.get_text(strip=True)
                gold_type = gold_type.replace("Vàng", "").replace("%", "").replace(",", "").replace("miếng SJC", "SJC").strip()
                buy_price = tds[0].get_text(strip=True).replace(".", "")
                if buy_price.isdigit():
                    gold_map[gold_type] = buy_price
                    logging.info(f"Loại vàng: {gold_type} | Giá mua vào: {buy_price}")
        logging.info(f"goldMap: {gold_map}")
        return gold_map, update_time
    except Exception as e:
        logging.error(f"Lỗi khi lấy giá vàng: {e}")
        return {}, ""

def update_sheet_mihong(spreadsheet_name, credentials_json):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_json, scope)
    client = gspread.authorize(creds)
    sheet = client.open(spreadsheet_name).worksheet("Trang tính1")

    gold_map, update_time = get_webgia_gold_prices()
    if not gold_map:
        print("Không lấy được dữ liệu giá vàng.")
        return

    # Ghi thời gian cập nhật vào ô H35 (nếu có)
    if update_time:
        sheet.update_acell('H35', update_time)
    else:
        sheet.update_acell('H35', "Không lấy được thời gian cập nhật")

    row = 36
    while True:
        try:
            type_cell = sheet.acell(f'G{row}').value
            if not type_cell:
                break
            type_norm = type_cell.strip()
            if type_norm.lower() != 'sjc':
                type_norm = ''.join(filter(str.isdigit, type_norm))
            if not type_norm:
                row += 1
                continue
            if type_norm in gold_map:
                price_string = gold_map[type_norm]
                try:
                    price_number = int(price_string)
                except:
                    row += 1
                    continue
                if price_number:
                    multiplied_price = price_number * 100
                    sheet.update_acell(f'H{row}', multiplied_price)
            row += 1
            if row > 500:
                break
        except Exception as e:
            print(f"Có lỗi xảy ra ở dòng {row}: {e}")
            break

if __name__ == "__main__":
    # Lấy credentials từ biến môi trường (GitHub Actions Secret)
    credentials_str = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not credentials_str:
        raise Exception("Chưa có biến môi trường GOOGLE_SHEETS_CREDENTIALS")
    credentials_json = json.loads(credentials_str)

    SPREADSHEET_NAME = "TIỀN HỤI"  # Đổi tên file Google Sheets ở đây
    update_sheet_mihong(SPREADSHEET_NAME, credentials_json)

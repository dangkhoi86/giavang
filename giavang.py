import os
import json
import requests
from bs4 import BeautifulSoup
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re # Import re module
import time # Import time module for delays

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def retry_with_backoff(func, max_retries=3, base_delay=1):
    """Retry function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 503 and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logging.warning(f"API Error 503, retrying in {delay} seconds... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            else:
                raise e
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logging.warning(f"Error occurred, retrying in {delay} seconds... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            else:
                raise e

def normalize_gold_type(gold_type_str):
    # Chuyển về chữ thường để so sánh không phân biệt hoa thường
    gold_type_str_lower = gold_type_str.lower()

    if "sjc" in gold_type_str_lower:
        return "SJC"
    elif "99,9%" in gold_type_str_lower or "99.9%" in gold_type_str_lower:
        return "999"
    elif "9t85" in gold_type_str_lower:
        return "985"
    elif "9t8" in gold_type_str_lower:
        return "980"
    elif "95" in gold_type_str_lower and "95,0%" in gold_type_str_lower:
        return "950"
    elif "v75" in gold_type_str_lower:
        return "750"
    elif "v68" in gold_type_str_lower:
        return "680"
    elif "6t1" in gold_type_str_lower:
        return "610"
    elif "14k" in gold_type_str_lower:
        return "14K"
    elif "10k" in gold_type_str_lower:
        return "10K"
    else:
        # Trường hợp dự phòng: thử trích xuất số và chữ cái, sau đó làm sạch
        cleaned = re.sub(r'[^\w]', '', gold_type_str) # Xóa các ký tự không phải chữ/số/gạch dưới
        cleaned = cleaned.replace("vang", "") # Xóa "vang" nếu nó còn sót lại
        return cleaned.upper() # Chuyển về chữ hoa cho đồng nhất

def get_webgia_gold_prices():
    url = "https://giavang.org/trong-nuoc/mi-hong/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        gold_data = []
        # Lấy thời gian cập nhật
        update_time = ""
        h1 = soup.find("h1", class_="box-headline highlight")
        if h1:
            small = h1.find("small")
            if small:
                update_time_full = small.get_text(strip=True)
                if "Cập nhật lúc" in update_time_full:
                    update_time = update_time_full.replace("Cập nhật lúc", "").strip()
                else:
                    update_time = update_time_full.strip()
        if update_time:
            logging.info(f"Thời gian cập nhật lấy được: {update_time}")
        else:
            logging.warning("Không lấy được thời gian cập nhật từ trang web!")
        # Lấy giá vàng
        # Tìm thẻ <thead> để lấy tiêu đề cột
        header_row = soup.find("thead").find("tr")
        headers = [th.get_text(strip=True) for th in header_row.find_all("th")]
        buy_index = -1
        sell_index = -1
        type_index = -1

        if "Mua vào" in headers:
            buy_index = headers.index("Mua vào")
        if "Bán ra" in headers:
            sell_index = headers.index("Bán ra")
        if "Loại vàng" in headers:
            type_index = headers.index("Loại vàng")

        if buy_index == -1 or sell_index == -1 or type_index == -1:
            logging.warning("Không tìm thấy đủ các cột cần thiết (Loại vàng, Mua vào, Bán ra).")
            return {}, ""

        for tr in soup.find("tbody").find_all("tr"): # Chỉ tìm trong tbody để tránh hàng tiêu đề
            tds = tr.find_all(["th", "td"]) # Có thể có cả th và td trong tbody
            if len(tds) > max(buy_index, sell_index, type_index):
                gold_type = tds[type_index].get_text(strip=True)
                buy_price = tds[buy_index].get_text(strip=True).replace(".", "").replace(",", "")
                sell_price = tds[sell_index].get_text(strip=True).replace(".", "").replace(",", "")

                # Chuẩn hóa loại vàng bằng hàm mới
                gold_type_normalized = normalize_gold_type(gold_type)

                gold_entry = {
                    "type": gold_type_normalized,
                    "buy_price": buy_price if buy_price.isdigit() else None,
                    "sell_price": sell_price if sell_price.isdigit() else None
                }
                gold_data.append(gold_entry)
                logging.info(f"Loại vàng: {gold_type_normalized} | Giá mua vào: {buy_price} | Giá bán ra: {sell_price}")

        # Chuyển gold_data thành gold_map nếu cần cho các hàm tiếp theo
        gold_map_for_return = {item["type"]: item for item in gold_data if item["buy_price"] is not None}
        logging.info(f"goldMap: {gold_map_for_return}")
        return gold_map_for_return, update_time
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
        retry_with_backoff(lambda: sheet.update_acell('H33', update_time))
    else:
        retry_with_backoff(lambda: sheet.update_acell('H33', "Không lấy được thời gian cập nhật"))

    # Thêm tiêu đề bảng ở M36, N36, O36
    retry_with_backoff(lambda: sheet.update('M16:O16', [["Loại vàng", "Mua vào", "Bán ra"]]))

    # Chuẩn bị dữ liệu batch cho cột M, N, O
    batch_data_mno = []
    current_row_mno = 17
    for gold_type, data in gold_map.items():
        type_to_write = gold_type
        buy_price_to_write = data.get("buy_price")
        sell_price_to_write = data.get("sell_price")

        # Chuyển đổi sang số và nhân với 100 nếu là số
        if buy_price_to_write and buy_price_to_write.isdigit():
            buy_price_to_write = int(buy_price_to_write) * 100
        else:
            buy_price_to_write = None # Hoặc giữ nguyên giá trị gốc nếu không phải số
        
        if sell_price_to_write and sell_price_to_write.isdigit():
            sell_price_to_write = int(sell_price_to_write) * 100
        else:
            sell_price_to_write = None # Hoặc giữ nguyên giá trị gốc nếu không phải số
        
        # Chuẩn bị dữ liệu cho một hàng
        row_data = [
            type_to_write,
            buy_price_to_write,
            sell_price_to_write
        ]
        batch_data_mno.append(row_data)
        logging.info(f"Prepared data for M{current_row_mno}:O{current_row_mno}: {row_data}")
        current_row_mno += 1

    # Batch update cho cột M, N, O
    if batch_data_mno:
        start_row = 17
        end_row = start_row + len(batch_data_mno) - 1
        range_name = f'M{start_row}:O{end_row}'
        retry_with_backoff(lambda: sheet.update(range_name, batch_data_mno))
        logging.info(f"Batch updated {range_name} with {len(batch_data_mno)} rows")
        time.sleep(1)  # Delay after batch update

    # Chuẩn bị dữ liệu batch cho cột H
    batch_data_h = []
    row_numbers = []
    row = 34
    while True:
        try:
            type_cell = retry_with_backoff(lambda: sheet.acell(f'G{row}').value)
            logging.info(f"Sheet cell G{row} raw value: {type_cell}")
            if not type_cell:
                break
            type_norm = type_cell.strip()
            logging.info(f"Sheet cell G{row} stripped value: {type_norm}")
            # Chuẩn hóa type_norm bằng hàm mới
            type_norm_key = normalize_gold_type(type_norm)

            logging.info(f"Sheet cell G{row} normalized key: {type_norm_key}")

            if not type_norm_key:
                row += 1
                continue

            if type_norm_key in gold_map:
                logging.info(f"Matching gold type '{type_norm_key}' found in gold_map.")
                buy_price_string = gold_map[type_norm_key].get("buy_price")
                sell_price_string = gold_map[type_norm_key].get("sell_price")
                logging.info(f"Prices for {type_norm_key}: Buy={buy_price_string}, Sell={sell_price_string}")

                buy_price_number = None
                sell_price_number = None

                if buy_price_string and buy_price_string.isdigit():
                    buy_price_number = int(buy_price_string)
                if sell_price_string and sell_price_string.isdigit():
                    sell_price_number = int(sell_price_string)

                # Chuẩn bị dữ liệu cho cột H
                if buy_price_number is not None:
                    multiplied_buy_price = buy_price_number * 100
                    batch_data_h.append([multiplied_buy_price])
                    row_numbers.append(row)
                    logging.info(f"Prepared H{row} with buy price: {multiplied_buy_price}")
            else:
                logging.warning(f"No match found for gold type '{type_norm_key}' in gold_map.")

            row += 1
            if row > 500:
                break
        except Exception as e:
            logging.error(f"Có lỗi xảy ra ở dòng {row}: {e}")
            break

    # Batch update cho cột H
    if batch_data_h:
        for i, (row_num, price_data) in enumerate(zip(row_numbers, batch_data_h)):
            try:
                retry_with_backoff(lambda: sheet.update_acell(f'H{row_num}', price_data[0]))
                logging.info(f"Updated H{row_num} with buy price: {price_data[0]}")
                if i < len(batch_data_h) - 1:  # Không delay sau lần update cuối
                    time.sleep(0.5)  # Delay giữa các update để tránh rate limiting
            except Exception as e:
                logging.error(f"Failed to update H{row_num}: {e}")

    # In danh sách sheets
    try:
        for sheet in client.openall():
            print(sheet.title)
    except Exception as e:
        logging.error(f"Error listing sheets: {e}")

if __name__ == "__main__":
    credentials_str = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if credentials_str:
        credentials_json = json.loads(credentials_str)
    else:
        # Nếu không có biến môi trường thì đọc từ file credentials.json
        with open('credentials.json', 'r', encoding='utf-8') as f:
            credentials_json = json.load(f)

    SPREADSHEET_NAME = "TIỀN HỤI"  # Đổi tên file Google Sheets ở đây
    update_sheet_mihong(SPREADSHEET_NAME, credentials_json)

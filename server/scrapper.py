import uuid, os, requests, yaml
from config import PAGEDIR
from datacontroller import init_page

for i in range(1):
    url = "https://fakerapi.it/api/v2/texts?_quantity=100&_characters=2048"

    # Fetch
    res = requests.get(url)
    data = res.json()["data"]

    for entry in data:
        init_page(title=entry['title'], base_text=entry['content'], genre=entry['genre'], author=entry['genre'])
        continue
        rand_dt = random_datetime(start_date, end_date)

        # Folder path from random datetime
        try:
            folder_path = os.path.join(PAGEDIR, str(rand_dt.year), f"{rand_dt.month:02}", f"{rand_dt.day:02}")
            os.makedirs(folder_path, exist_ok=True)
        except PermissionError as e:
            print(f"Permission error: {e}")
            exit()


        # Generate UUID5 using title + timestamp
        file_uuid = str(uuid.uuid5(NAMESPACE, entry['title'] + str(rand_dt.timestamp()))).replace('-', '')

        # Markdown content with YAML front matter
        yaml_config = {
            "uuid": file_uuid,
            "type": "article",
            "date": rand_dt.strftime('%Y-%m-%d %H:%M:%S'),
            "creator": entry['genre'],
            "title": entry['title'],
        }
        md_content = f"---\n{yaml.safe_dump(yaml_config)}---\n\n{entry['content']}"

        # Save file with UUID as filename and .md extension
        filepath = os.path.join(folder_path, f"{file_uuid}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)
            

print("100 Scrapped")
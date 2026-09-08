import json
import os
import random

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "data", "catalog.json")

IMAGE_SEEDS = {
    "footwear": [
        "https://images.unsplash.com/photo-1542291026-7eec264c27ff",
        "https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a",
        "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77",
        "https://images.unsplash.com/photo-1560769629-975ec94e6a86",
        "https://images.unsplash.com/photo-1584735935682-2f2b69dff9d2",
        "https://images.unsplash.com/photo-1549298916-b41d501d3772",
        "https://images.unsplash.com/photo-1608231387042-66d1773070a5",
        "https://images.unsplash.com/photo-1607522370275-f14206abe5d3",
        "https://images.unsplash.com/photo-1575537302964-96cd47c06b1b",
        "https://images.unsplash.com/photo-1539185441755-769473a23570",
    ],
    "electronics": [
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e",
        "https://images.unsplash.com/photo-1546868871-7041f2a55e12",
        "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed",
        "https://images.unsplash.com/photo-1572569511254-d8f925fe2cbb",
        "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf",
        "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9",
        "https://images.unsplash.com/photo-1583394838336-acd977736f90",
        "https://images.unsplash.com/photo-1590658268037-6bf12165a8df",
        "https://images.unsplash.com/photo-1563245372-f21724e3856d",
        "https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb",
    ],
    "apparel": [
        "https://images.unsplash.com/photo-1521572267360-ee0c2909d518",
        "https://images.unsplash.com/photo-1576566588028-4147f3842f27",
        "https://images.unsplash.com/photo-1618354691373-d851c5c3a990",
        "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c",
        "https://images.unsplash.com/photo-1551028719-00167b16eac5",
        "https://images.unsplash.com/photo-1591047139829-d91aecb6caea",
        "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633",
        "https://images.unsplash.com/photo-1562157873-818bc0726f68",
        "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf",
        "https://images.unsplash.com/photo-1578932750294-f5075e85f44a",
    ],
    "accessories": [
        "https://images.unsplash.com/photo-1627123424574-724758594e93",
        "https://images.unsplash.com/photo-1553062407-98eeb64c6a62",
        "https://images.unsplash.com/photo-1509741102003-ca64bfe5f069",
        "https://images.unsplash.com/photo-1511499767150-a48a237f0083",
        "https://images.unsplash.com/photo-1584917865442-de89df76afd3",
        "https://images.unsplash.com/photo-1622560480605-d83c853bc5c3",
        "https://images.unsplash.com/photo-1590874103328-eac38a683ce7",
        "https://images.unsplash.com/photo-1575428652377-a2d80e2277fc",
        "https://images.unsplash.com/photo-1588180596407-42289656209e",
        "https://images.unsplash.com/photo-1548036328-c9fa89d128fa",
    ],
    "home & living": [
        "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd",
        "https://images.unsplash.com/photo-1507473885765-e6ed057f782c",
        "https://images.unsplash.com/photo-1586023492125-27b2c045efd7",
        "https://images.unsplash.com/photo-1513519245088-0e12902e5a38",
        "https://images.unsplash.com/photo-1534349762230-e0cadf78f5da",
        "https://images.unsplash.com/photo-1583847268964-b28dc8f51f92",
        "https://images.unsplash.com/photo-1517705008128-361805f42e86",
        "https://images.unsplash.com/photo-1579656381226-5fc0f0100c3b",
        "https://images.unsplash.com/photo-1544816155-12df9643f363",
        "https://images.unsplash.com/photo-1600585154340-be6161a56a0c",
    ],
    "sports & fitness": [
        "https://images.unsplash.com/photo-1584735935682-2f2b69dff9d2",
        "https://images.unsplash.com/photo-1517838277536-f5f99be501cd",
        "https://images.unsplash.com/photo-1575052814086-f385e2e2ad1b",
        "https://images.unsplash.com/photo-1598971861713-54ad16a7e72e",
        "https://images.unsplash.com/photo-1581009146145-b5ef050c2e1e",
        "https://images.unsplash.com/photo-1598289431512-b97b0917affc",
        "https://images.unsplash.com/photo-1540497077202-7c8a3999166f",
        "https://images.unsplash.com/photo-1518611012118-696072aa579a",
        "https://images.unsplash.com/photo-1526506118085-60ce8714f8c5",
        "https://images.unsplash.com/photo-1574680096145-d05b474e2155",
    ],
    "gaming & tech": [
        "https://images.unsplash.com/photo-1542751371-adc38448a05e",
        "https://images.unsplash.com/photo-1612287233207-6c2e35b71946",
        "https://images.unsplash.com/photo-1526738549149-8e07eca6c147",
        "https://images.unsplash.com/photo-1616588589676-62b3bd4ff6d2",
        "https://images.unsplash.com/photo-1587202372775-e229f172b9d7",
        "https://images.unsplash.com/photo-1592840496694-26d035b52b48",
        "https://images.unsplash.com/photo-1550745165-9bc0b252726f",
        "https://images.unsplash.com/photo-1538481199705-c710c4e965fc",
        "https://images.unsplash.com/photo-1547394765-185e1e68f34e",
        "https://images.unsplash.com/photo-1593305841991-05c297ba4575",
    ],
    "beauty & personal care": [
        "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e",
        "https://images.unsplash.com/photo-1556228720-195a672e8a03",
        "https://images.unsplash.com/photo-1608248597359-00994f71a179",
        "https://images.unsplash.com/photo-1598440947619-2c35fc9aa908",
        "https://images.unsplash.com/photo-1571781926291-c477ebfd024b",
        "https://images.unsplash.com/photo-1596462502278-27bfdc403348",
        "https://images.unsplash.com/photo-1526947425960-945c6e72858f",
        "https://images.unsplash.com/photo-1535585209827-a15fcdbc4c2d",
        "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881",
        "https://images.unsplash.com/photo-1601049541289-9b1b7bbbfe19",
    ],
    "watches & jewelry": [
        "https://images.unsplash.com/photo-1524805444758-089113d48a6d",
        "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9",
        "https://images.unsplash.com/photo-1533139502658-0198f920d8e8",
        "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f",
        "https://images.unsplash.com/photo-1617043786394-f977fa12eddf",
        "https://images.unsplash.com/photo-1535683577427-740aaac4ecfa",
        "https://images.unsplash.com/photo-1515562141207-7a88fb7ce338",
        "https://images.unsplash.com/photo-1605100804763-247f67b3557e",
        "https://images.unsplash.com/photo-1600003014755-ba31aa59c4b6",
        "https://images.unsplash.com/photo-1594576722512-582bcd04f477",
    ],
    "books & stationery": [
        "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c",
        "https://images.unsplash.com/photo-1589829085413-56de8ae18c73",
        "https://images.unsplash.com/photo-1512820790803-83ca734da794",
        "https://images.unsplash.com/photo-1532012164546-f432f2e3777f",
        "https://images.unsplash.com/photo-1544947950-fa07a98d237f",
        "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8",
        "https://images.unsplash.com/photo-1516962215378-7fa2e137ae93",
        "https://images.unsplash.com/photo-1497633762265-9d179a990aa6",
        "https://images.unsplash.com/photo-1506880018603-83d5b814b5a6",
        "https://images.unsplash.com/photo-1495446815901-a7297e633e8d",
    ]
}

ADJECTIVES = [
    "Pro", "Ultra", "Classic", "Premium", "Elite", "Urban", "Vanguard", "Apex", "Minimalist",
    "Signature", "Prime", "Studio", "Hyper", "Carbon", "Nordic", "Matrix", "Aero", "Pulse",
    "Titanium", "Velocity", "Flex", "Evo", "Stealth", "Zenith", "Breeze", "Infinite", "Nexus"
]

CATEGORY_TEMPLATES = {
    "footwear": [
        ("Running Shoes", ["shoes", "running", "sports", "footwear"], (1999, 5999)),
        ("Trail Sneaker", ["shoes", "sneakers", "trail", "outdoor"], (2499, 6499)),
        ("Chelsea Leather Boots", ["boots", "leather", "casual", "formal"], (3499, 8999)),
        ("Slip-on Loafers", ["loafers", "shoes", "casual", "smart"], (1799, 4999)),
        ("Oxford Formal Derby", ["shoes", "formal", "leather", "office"], (2999, 7999)),
        ("High-Top Canvas Sneakers", ["sneakers", "canvas", "streetwear", "casual"], (1499, 3999)),
        ("Cushioned Slides", ["sandals", "slides", "comfort", "casual"], (799, 1999)),
        ("Carbon Fiber Marathon Racer", ["shoes", "running", "performance", "marathon"], (6999, 9999)),
    ],
    "electronics": [
        ("True Wireless ANC Earbuds", ["audio", "earbuds", "wireless", "anc"], (1499, 4999)),
        ("Over-Ear Noise Cancelling Headphones", ["audio", "headphones", "wireless", "anc"], (3999, 9999)),
        ("Smartwatch with AMOLED Display", ["smartwatch", "wearable", "fitness", "tech"], (2999, 8999)),
        ("Mechanical RGB Gaming Keyboard", ["keyboard", "gaming", "electronics", "rgb"], (2499, 6999)),
        ("Ergonomic Wireless Mouse", ["mouse", "wireless", "ergonomic", "office"], (999, 3499)),
        ("65W GaN Fast Charger", ["charger", "gan", "fast charging", "usb-c"], (1299, 2999)),
        ("20000mAh Power Bank", ["power bank", "battery", "portable", "charging"], (1499, 3999)),
        ("Bluetooth Waterproof Speaker", ["speaker", "audio", "bluetooth", "portable"], (1899, 6499)),
        ("4K Ultra HD Action Camera", ["camera", "action", "4k", "video"], (5499, 9999)),
        ("Magnetic Wireless Power Stand", ["charging", "wireless", "desk", "accessories"], (1799, 3999)),
    ],
    "apparel": [
        ("Oversized Heavyweight T-Shirt", ["tshirt", "cotton", "oversized", "streetwear"], (799, 1699)),
        ("Slim-Tapered Stretch Denim", ["jeans", "denim", "pants", "casual"], (1899, 3999)),
        ("French Terry Hoodie", ["hoodie", "sweatshirt", "winter", "comfort"], (1999, 4499)),
        ("Linen Mandarin Collar Shirt", ["shirt", "linen", "summer", "casual"], (1599, 3499)),
        ("Athletic Tech Joggers", ["joggers", "pants", "athletic", "gym"], (1299, 2799)),
        ("Wool Blend Tailored Blazer", ["blazer", "formal", "suit", "jacket"], (4999, 9999)),
        ("Water-Resistant Bomber Jacket", ["jacket", "outerwear", "bomber", "streetwear"], (2999, 6999)),
        ("Breathable Pique Polo", ["polo", "shirt", "casual", "smart"], (999, 2299)),
        ("Pure Cotton Relaxed Shorts", ["shorts", "casual", "summer", "cotton"], (699, 1499)),
    ],
    "accessories": [
        ("RFID Blocking Slim Wallet", ["wallet", "leather", "rfid", "accessories"], (899, 2499)),
        ("Polarized Aviator Sunglasses", ["sunglasses", "eyewear", "polarized", "summer"], (1299, 3999)),
        ("Water-Resistant Commuter Backpack", ["backpack", "bag", "laptop", "travel"], (1999, 4999)),
        ("Full-Grain Leather Belt", ["belt", "leather", "formal", "casual"], (899, 2199)),
        ("Minimalist Crossbody Bag", ["bag", "crossbody", "travel", "streetwear"], (1299, 2999)),
        ("Aerospace Aluminum Card Holder", ["cardholder", "metal", "minimalist", "wallet"], (699, 1899)),
        ("Canvas Weekend Duffle Bag", ["duffle", "bag", "travel", "gym"], (2499, 5999)),
        ("Silicone Sports Strap for Watch", ["strap", "watch", "accessories", "sports"], (499, 1299)),
    ],
    "home & living": [
        ("Ceramic Pour-Over Coffee Mug", ["mug", "ceramic", "coffee", "kitchen"], (499, 1299)),
        ("Minimalist LED Desk Lamp", ["lamp", "lighting", "desk", "home"], (1299, 3499)),
        ("Ultrasonic Essential Oil Diffuser", ["diffuser", "aroma", "wellness", "home"], (1499, 3299)),
        ("Memory Foam Ergonomic Seat Cushion", ["cushion", "ergonomic", "office", "comfort"], (1199, 2699)),
        ("Double-Walled Insulated Flask", ["bottle", "flask", "insulated", "water"], (799, 1999)),
        ("Nordic Matte Ceramic Planter", ["planter", "pot", "decor", "plants"], (599, 1699)),
        ("Silent Sweep Wall Clock", ["clock", "decor", "minimalist", "home"], (999, 2499)),
        ("Hand-Poured Soy Wax Scented Candle", ["candle", "scented", "aromatherapy", "decor"], (699, 1599)),
    ],
    "sports & fitness": [
        ("Adjustable Quick-Select Dumbbell", ["dumbbell", "weights", "gym", "fitness"], (3999, 9999)),
        ("Extra-Thick Non-Slip Yoga Mat", ["yoga", "mat", "fitness", "workout"], (999, 2499)),
        ("Heavy-Duty Resistance Loop Bands", ["resistance bands", "fitness", "workout", "strength"], (599, 1499)),
        ("High-Speed Bearing Jump Rope", ["jump rope", "cardio", "fitness", "crossfit"], (499, 1199)),
        ("Insulated Protein Shaker Bottle", ["shaker", "bottle", "gym", "supplements"], (699, 1699)),
        ("High-Density Deep Tissue Foam Roller", ["foam roller", "recovery", "massage", "fitness"], (899, 1999)),
        ("Padded Weightlifting Gym Gloves", ["gloves", "gym", "lifting", "training"], (599, 1399)),
    ],
    "gaming & tech": [
        ("Extended RGB Gaming Desk Mat", ["mousepad", "gaming", "rgb", "desk"], (899, 2199)),
        ("Studio USB Condenser Microphone", ["microphone", "audio", "streaming", "podcast"], (2499, 6999)),
        ("Ergonomic Monitor Desk Arm", ["monitor arm", "desk", "ergonomic", "setup"], (1999, 4999)),
        ("Wireless Dual-Vibration Controller", ["controller", "gamepad", "gaming", "pc"], (1899, 4499)),
        ("RGB Laptop Cooling Stand", ["cooling pad", "laptop", "gaming", "accessories"], (1299, 2899)),
        ("Magnetic Cable Management Hub", ["cable organizer", "desk", "tech", "accessories"], (499, 1299)),
    ],
    "beauty & personal care": [
        ("Organic Beard Grooming Oil", ["beard oil", "grooming", "men", "skincare"], (499, 1299)),
        ("Vitamin C Radiance Face Serum", ["serum", "skincare", "beauty", "face"], (699, 1799)),
        ("Waterproof Electric Foil Shaver", ["shaver", "grooming", "trimmer", "men"], (1999, 4999)),
        ("Sonic Oscillating Toothbrush", ["toothbrush", "dental", "electric", "hygiene"], (1499, 3999)),
        ("Matte Finish Styling Clay Pomade", ["hair pomade", "styling", "grooming", "hair"], (499, 1199)),
        ("Broad Spectrum Invisible Sunscreen", ["sunscreen", "skincare", "spf", "summer"], (599, 1499)),
    ],
    "watches & jewelry": [
        ("Stainless Steel Chronograph Watch", ["watch", "chronograph", "luxury", "accessories"], (4499, 9999)),
        ("Minimalist Sapphire Quartz Watch", ["watch", "quartz", "minimalist", "classic"], (2999, 7999)),
        ("Brushed Titanium Band Ring", ["ring", "titanium", "jewelry", "mens"], (899, 2499)),
        ("Braided Leather & Steel Bracelet", ["bracelet", "leather", "jewelry", "accessories"], (699, 1899)),
        ("Automatic 200m Diver Watch", ["watch", "automatic", "diver", "waterproof"], (6999, 9999)),
    ],
    "books & stationery": [
        ("Lay-Flat Dot Grid Hardcover Journal", ["journal", "notebook", "stationery", "planning"], (499, 1299)),
        ("Brass Piston Fountain Pen", ["pen", "fountain pen", "stationery", "luxury"], (999, 2999)),
        ("Archival Quality Fineliner Set", ["pens", "drawing", "stationery", "art"], (699, 1599)),
        ("Full-Grain Leather Desk Pad", ["desk pad", "leather", "stationery", "office"], (1499, 3499)),
        ("Minimalist Daily Productivity Planner", ["planner", "journal", "productivity", "stationery"], (599, 1499)),
    ]
}

COLORS = [
    "Matte Black", "Midnight Navy", "Stealth Grey", "Arctic White", "Forest Green",
    "Burgundy Wine", "Desert Tan", "Cobalt Blue", "Smoky Charcoal", "Rose Gold",
    "Silver Metallic", "Espresso Brown", "Slate Blue", "Olive Drab", "Crimson Red"
]

def generate_full_catalog(target_count=10000):
    existing = []
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing_skus = {item["sku"] for item in existing}
    print(f"Loaded {len(existing)} existing products.")

    products = list(existing)
    categories = list(CATEGORY_TEMPLATES.keys())

    random.seed(42)  # Deterministic seed

    current_idx = 1
    for item in existing:
        sku = item.get("sku", "")
        if sku.startswith("SH"):
            try:
                num = int(sku[2:])
                if num >= current_idx:
                    current_idx = num + 1
            except ValueError:
                pass

    while len(products) < target_count:
        sku = f"SH{current_idx:05d}"
        current_idx += 1
        if sku in existing_skus:
            continue

        cat = random.choice(categories)
        templates = CATEGORY_TEMPLATES[cat]
        base_name, tags, price_range = random.choice(templates)
        adj = random.choice(ADJECTIVES)
        color = random.choice(COLORS)

        style = random.randint(1, 4)
        if style == 1:
            name = f"{adj} {base_name} - {color}"
        elif style == 2:
            name = f"{color} {adj} {base_name}"
        elif style == 3:
            name = f"{adj} {base_name} Gen {random.randint(2, 5)}"
        else:
            name = f"{base_name} ({adj} Edition - {color})"

        price = random.randint(price_range[0] // 50, price_range[1] // 50) * 50 - 1
        if price > 10000:
            price = 9999
        elif price < 199:
            price = 299

        stock = random.randint(5, 50)

        img_base = random.choice(IMAGE_SEEDS[cat])
        image_url = f"{img_base}?auto=format&fit=crop&w=900&q=80&sig={sku}"

        product_tags = list(set(tags + [
            cat.replace(" & ", "_").replace(" ", "_"),
            color.lower().replace(" ", "_"),
            adj.lower()
        ]))

        product = {
            "sku": sku,
            "name": name,
            "category": cat,
            "price": price,
            "stock": stock,
            "tags": product_tags,
            "image": image_url
        }

        products.append(product)
        existing_skus.add(sku)

    # Add signature items right at spend cap limit (Rs. 10,000)
    products[-1]["price"] = 10000
    products[-1]["name"] = "Titanium Pro Master Diver Watch (10k Spend Cap Ceiling)"
    products[-1]["category"] = "watches & jewelry"
    products[-2]["price"] = 9999
    products[-2]["name"] = "Carbon Fiber Pro Elite Road Bike Helmet"
    products[-2]["category"] = "sports & fitness"

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    print(f"Successfully generated {len(products)} products in {CATALOG_PATH}")

if __name__ == "__main__":
    generate_full_catalog(10000)

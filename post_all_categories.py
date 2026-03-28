import urllib.request
import json
import time

articles = [
    {
        "title": "U.S. President Announces New Executive Actions on Federal Employee Pay and DHS Equity",
        "slug": "us-president-executive-actions-federal-pay-dhs-2026",
        "excerpt": "In a series of late-March moves, the White House introduced new measures aimed at increasing TSA employee pay and enhancing equity within the Department of Homeland Security.",
        "content_html": "<h2>New Executive Directives Focus on Federal Workforce</h2><p>The U.S. administration has unveiled a comprehensive set of executive actions designed to overhaul pay structures for Transportation Security Administration (TSA) employees and broaden equity initiatives within the Department of Homeland Security (DHS).</p><p><strong>Addressing the Pay Gap</strong></p><p>A primary component of the new directives is a significant adjustment to the TSA's pay scales, aligning them more closely with other federal law enforcement agencies. Proponents argue this move is essential for improving retention rates and morale among frontline security personnel who have long advocated for pay parity.</p><p><strong>Equity and Inclusion in National Security</strong></p><p>The actions also mandate new reporting requirements and internal reviews aimed at identifying and mitigating systemic biases in DHS recruitment and promotion processes. \"A diverse and equitable workforce is a stronger workforce,\" stated the DHS Secretary during the announcement event at the Ronald Reagan Building.</p><p><strong>Political and Fiscal Implications</strong></p><p>Critics in Congress have raised concerns regarding the long-term fiscal impact of the pay increases, calling for detailed budget offsets. However, labor unions representing federal employees have praised the move as a long-overdue victory for civil service workers.</p>",
        "featured_image": None,
        "image_caption": None,
        "type": "news",
        "status": "published",
        "author": {
            "id": "harsh-sanghani",
            "slug": "harsh-sanghani",
            "name": "Harsh Sanghani"
        },
        "category": {
            "id": "696ca7a5ecbd8aee584d42a5",
            "name": "Politics",
            "slug": "politics"
        },
        "topics": [
            {"name": "US Politics", "slug": "us-politics"},
            {"name": "Federal Workforce", "slug": "federal-workforce"},
            {"name": "DHS", "slug": "dhs"},
            {"name": "TSA", "slug": "tsa"}
        ],
        "is_featured": True,
        "published_at": "2026-03-27T10:00:00Z"
    },
    {
        "title": "Bank of America Settles with Jeffrey Epstein Victims for Record Sum",
        "slug": "bank-of-america-settlement-epstein-victims-2026",
        "excerpt": "Bank of America has reached a definitive settlement with victims of Jeffrey Epstein, resolving long-standing legal claims regarding the bank's alleged role in facilitating the late financier's network.",
        "content_html": "<h2>Major Settlement Concludes Multi-Year Legal Battle</h2><p>In a historic legal resolution, Bank of America has agreed to pay a record-breaking sum to settle claims brought by victims of Jeffrey Epstein. The settlement addresses allegations that the financial institution failed to flag suspicious activity related to Epstein's accounts over several years.</p><p><strong>Accountability in the Financial Sector</strong></p><p>Legal representatives for the survivors described the settlement as a landmark moment for financial accountability. \"This agreement isn't just about the money; it's about holding powerful institutions responsible for their oversight failures,\" said one of the lead attorneys during a press conference in Manhattan.</p><p><strong>Bank Statement</strong></p><p>While the bank did not admit to any wrongdoing as part of the settlement, a spokesperson released a statement reiterating the company's commitment to rigorous anti-money laundering and know-your-customer protocols. The funds from the settlement are expected to be distributed through a court-approved compensation fund.</p><p><strong>Impact on Wall Street</strong></p><p>Financial analysts suggest that this settlement may prompt other large banks to conduct deeper internal reviews of high-profile client relationships. The resolution marks one of the final major civil actions related to Epstein's financial network.</p>",
        "featured_image": None,
        "image_caption": None,
        "type": "news",
        "status": "published",
        "author": {
            "id": "harsh-sanghani",
            "slug": "harsh-sanghani",
            "name": "Harsh Sanghani"
        },
        "category": {
            "id": "696ca7acecbd8aee584d42a6",
            "name": "Business",
            "slug": "business"
        },
        "topics": [
            {"name": "Banking", "slug": "banking"},
            {"name": "Wall Street", "slug": "wall-street"},
            {"name": "Legal Settlement", "slug": "legal-settlement"},
            {"name": "Financial Oversight", "slug": "financial-oversight"}
        ],
        "is_featured": False,
        "published_at": "2026-03-26T14:30:00Z"
    },
    {
        "title": "Vietnam Concludes National Assembly Elections Amid Economic Pivot",
        "slug": "vietnam-national-assembly-elections-2026",
        "excerpt": "Vietnam successfully held its National Assembly elections in mid-March, as the country continues its strategic pivot toward high-tech manufacturing and digital infrastructure.",
        "content_html": "<h2>Stability and Reform Define 2026 Elections</h2><p>Vietnam has concluded its latest round of elections for the National Assembly, with official results showing a strong mandate for continued economic reform and regional integration. The election cycle occurred during a pivotal moment as the nation seeks to elevate its status in the global semiconductor supply chain.</p><p><strong>Economic Modernization</strong></p><p>The newly elected assembly is expected to prioritize legislation that simplifies foreign direct investment (FDI) in the technology sector. \"Our goal is to transition from a labor-intensive economy to a technology-driven powerhouse,\" said an official from the Ministry of Planning and Investment.</p><p><strong>Regional Diplomacy</strong></p><p>International observers noted the high voter turnout across Hanoi and Ho Chi Minh City. Diplomatic analysts believe the election results will reinforce Vietnam's balanced approach to international relations, maintaining strong ties with major global powers while strengthening ASEAN cooperation.</p><p><strong>Future Outlook</strong></p><p>Over the next five years, the Vietnamese government plans to invest heavily in green energy and 5G infrastructure, aiming to achieve sustainable growth while navigating global economic headwinds.</p>",
        "featured_image": None,
        "image_caption": None,
        "type": "news",
        "status": "published",
        "author": {
            "id": "harsh-sanghani",
            "slug": "harsh-sanghani",
            "name": "Harsh Sanghani"
        },
        "category": {
            "id": "696ca7bdecbd8aee584d42a8",
            "name": "World",
            "slug": "world"
        },
        "topics": [
            {"name": "Vietnam", "slug": "vietnam"},
            {"name": "Global Elections", "slug": "global-elections"},
            {"name": "International Business", "slug": "international-business"},
            {"name": "ASEAN", "slug": "asean"}
        ],
        "is_featured": False,
        "published_at": "2026-03-25T11:00:00Z"
    },
    {
        "title": "Reflecting on International Women's Day: The State of Global Equality in 2026",
        "slug": "international-womens-day-reflections-2026",
        "excerpt": "Opinion: Following this month's global observances, it is clear that while significant strides have been made in political representation, the economic empowerment gap remains a critical challenge.",
        "content_html": "<h2>Progress and Persistence in the Quest for Parity</h2><p>As the curtains close on the month of March, we reflect on the recent International Women's Day observances. The the year 2026 has provided a clear-eyed view of where the global movement for equality stands: we are seeing record levels of female leadership in climate science and technology, yet structural barriers in the 'care economy' persist.</p><p><strong>The Resilience of the Pay Gap</strong></p><p>Despite corporate pledges and legislative efforts, the global gender pay gap has remained stubbornly stagnant in several high-growth industries. Real equality requires more than just equal opportunity; it requires an fundamental re-evaluation of how we value domestic labor and childcare infrastructure.</p><p><strong>A New Generation of Leadership</strong></p><p>One of the most inspiring trends of 2026 is the surge of young women leading grassroots digital rights movements across the Global South. These leaders are not just fighting for representation; they are redesigning the systems of the future with inclusivity at their core.</p><p><strong>The Path Forward</strong></p><p>The lessons of this month are simple but profound. Equality is not a destination but a continuous process of dismantling outdated norms and rebuilding more resilient, equitable communities for everyone.</p>",
        "featured_image": None,
        "image_caption": None,
        "type": "opinion",
        "status": "published",
        "author": {
            "id": "harsh-sanghani",
            "slug": "harsh-sanghani",
            "name": "Harsh Sanghani"
        },
        "category": {
            "id": "696ca804ecbd8aee584d42a9",
            "name": "Opinion",
            "slug": "opinion"
        },
        "topics": [
            {"name": "Equality", "slug": "equality"},
            {"name": "Leadership", "slug": "leadership"},
            {"name": "Human Rights", "slug": "human-rights"},
            {"name": "Global Society", "slug": "global-society"}
        ],
        "is_featured": False,
        "published_at": "2026-03-28T09:00:00Z"
    },
    {
        "title": "NCAA March Madness 2026: Historic Upsets Define the Opening Rounds",
        "slug": "ncaa-march-madness-historic-upsets-2026",
        "excerpt": "College basketball fans witnessed a series of unprecedented upsets during the first week of March Madness 2026, as underdog programs toppled multiple top seeds in the quest for the national title.",
        "content_html": "<h2>The Madness Lives Up to Its Name</h2><p>The 2026 NCAA Division I Men's and Women's Basketball Tournaments have officially entered the 'Sweet Sixteen' phase, following one of the most unpredictable opening weeks in tournament history. Fans and bracket-makers alike were stunned as three separate 14-seeds advanced past the first round.</p><p><strong>Cinderella Stories Abound</strong></p><p>In the Men's bracket, the University of North Florida's dramatic overtime victory against the defending champions was hailed as the defining moment of the 'First Round.' Meanwhile, on the Women's side, a relentless defensive display from the 12-seeded Buffalo Bulls secured their first-ever trip to the regional semifinals.</p><p><strong>Economic Impact of the Tournament</strong></p><p>Host cities including Indianapolis and Atlanta reported record attendance and tourism revenue, highlighting the enduring economic power of college athletics. Television ratings for the opening rounds also saw a significant spike, driven by the compelling 'underdog' narratives dominating the 2026 cycle.</p><p><strong>A New Era of Competition</strong></p><p>Sports analysts attribute the increased parity in the tournament to the continued evolution of player transfer rules and advanced data analytics, which have allowed smaller programs to compete more effectively with traditional powerhouses. The road to the Final Four in Dallas is now wide open.</p>",
        "featured_image": None,
        "image_caption": None,
        "type": "news",
        "status": "published",
        "author": {
            "id": "harsh-sanghani",
            "slug": "harsh-sanghani",
            "name": "Harsh Sanghani"
        },
        "category": {
            "id": "698dff234880244851228bd1",
            "name": "Sports",
            "slug": "sports"
        },
        "topics": [
            {"name": "Basketball", "slug": "basketball"},
            {"name": "NCAA", "slug": "ncaa"},
            {"name": "March Madness", "slug": "march-madness"},
            {"name": "Sports Strategy", "slug": "sports-strategy"}
        ],
        "is_featured": True,
        "published_at": "2026-03-28T15:00:00Z"
    }
]

url = "http://127.0.0.1:5000/api/v1/admin/articles"

for article in articles:
    data = json.dumps(article).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Posted '{article['title']}' - Status: {response.getcode()} - Slug: {result.get('slug')}")
    except urllib.error.URLError as e:
        print(f"Failed '{article['title']}' - Error: {e}")
    time.sleep(1)

print("Finished posting all articles.")

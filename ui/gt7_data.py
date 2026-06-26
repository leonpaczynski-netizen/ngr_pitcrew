"""GT7 static reference data: track layouts, car list, and tyre temperature presets."""
from __future__ import annotations

import json
import os

from data.tyres import ALL_COMPOUNDS, normalise_code, get_by_code

GT7_TRACKS: list[str] = sorted([
    # --- Fictional circuits ---
    # Alsace
    "Alsace – Village",
    "Alsace – Village (Reverse)",
    "Alsace – Village Short",
    "Alsace – Village Short (Reverse)",
    # Autodromo Lago Maggiore
    "Autodromo Lago Maggiore – Full Course",
    "Autodromo Lago Maggiore – Full Course (Reverse)",
    "Autodromo Lago Maggiore – West",
    "Autodromo Lago Maggiore – West (Reverse)",
    "Autodromo Lago Maggiore – Center",
    "Autodromo Lago Maggiore – Center (Reverse)",
    "Autodromo Lago Maggiore – Porsche Cup",
    "Autodromo Lago Maggiore – Porsche Cup (Reverse)",
    "Autodromo Lago Maggiore – East Short",
    "Autodromo Lago Maggiore – East Short (Reverse)",
    "Autodromo Lago Maggiore – South",
    "Autodromo Lago Maggiore – South (Reverse)",
    # Blue Moon Bay
    "Blue Moon Bay Speedway",
    "Blue Moon Bay Speedway (Reverse)",
    "Blue Moon Bay Speedway – Infield A",
    "Blue Moon Bay Speedway – Infield A (Reverse)",
    "Blue Moon Bay Speedway – Infield B",
    "Blue Moon Bay Speedway – Infield B (Reverse)",
    # Broad Bean Raceway
    "Broad Bean Raceway",
    "Broad Bean Raceway (Reverse)",
    # Deep Forest
    "Deep Forest Raceway",
    "Deep Forest Raceway (Reverse)",
    # Dragon Trail
    "Dragon Trail – Seaside",
    "Dragon Trail – Seaside (Reverse)",
    "Dragon Trail – Gardens",
    "Dragon Trail – Gardens (Reverse)",
    # Eiger Nordwand
    "Eiger Nordwand – Short Track",
    "Eiger Nordwand – G Trail",
    # High-Speed Ring
    "High-Speed Ring",
    "High-Speed Ring (Reverse)",
    # Kyoto Driving Park
    "Kyoto Driving Park – Yamagiwa",
    "Kyoto Driving Park – Yamagiwa (Reverse)",
    "Kyoto Driving Park – Yamagiwa+Miyabi",
    "Kyoto Driving Park – Yamagiwa+Miyabi (Reverse)",
    "Kyoto Driving Park – Miyabi",
    "Kyoto Driving Park – Miyabi (Reverse)",
    # Northern Isle
    "Northern Isle Speedway",
    # Sainte-Croix
    "Sainte-Croix – Circuit A",
    "Sainte-Croix – Circuit A (Reverse)",
    "Sainte-Croix – Circuit B",
    "Sainte-Croix – Circuit B (Reverse)",
    "Sainte-Croix – Circuit C",
    "Sainte-Croix – Circuit C (Reverse)",
    # Sardegna (Road)
    "Sardegna – Road Track A",
    "Sardegna – Road Track A (Reverse)",
    "Sardegna – Road Track B",
    "Sardegna – Road Track B (Reverse)",
    "Sardegna – Road Track C",
    "Sardegna – Road Track C (Reverse)",
    # Special Stage Route X
    "Special Stage Route X",
    # Tokyo Expressway
    "Tokyo Expressway – Central Outer Loop",
    "Tokyo Expressway – Central Outer Loop (Reverse)",
    "Tokyo Expressway – Central Inner Loop",
    "Tokyo Expressway – Central Inner Loop (Reverse)",
    "Tokyo Expressway – South Outer Loop",
    "Tokyo Expressway – South Inner Loop",
    # Trial Mountain
    "Trial Mountain Circuit",
    "Trial Mountain Circuit (Reverse)",
    # --- Real-world circuits ---
    "Autopolis – International Racing Course",
    "Autopolis – Short Course",
    "Autodromo Nazionale Monza",
    "Autodromo Nazionale Monza – Junior Circuit",
    "Barcelona – Circuit de Catalunya",
    "Barcelona – Circuit de Catalunya – Club Circuit",
    "Barcelona – Rallycross Circuit",
    "Bathurst – Mount Panorama Motor Racing Circuit",
    "Brands Hatch – Indy Circuit",
    "Brands Hatch – Grand Prix Circuit",
    "Circuit de la Sarthe",
    "Circuit de la Sarthe (No Chicane)",
    "Daytona – Road Course",
    "Daytona – Tri-Oval",
    "Fuji Speedway",
    "Fuji Speedway – Short",
    "Goodwood Motor Circuit",
    "Interlagos – Autódromo José Carlos Pace",
    "Laguna Seca – WeatherTech Raceway",
    "Nürburgring – Nordschleife",
    "Nürburgring – Nordschleife (24h Configuration)",
    "Nürburgring – Nordschleife (Industriefahrten)",
    "Nürburgring – Grand Prix",
    "Nürburgring – GP Sprint Short",
    "Nürburgring – Sprint Short",
    "Red Bull Ring – Grand Prix",
    "Red Bull Ring – Short",
    "Road Atlanta",
    "Spa-Francorchamps",
    "Spa-Francorchamps (Reverse)",
    "Suzuka Circuit",
    "Suzuka Circuit – East Course",
    "Tsukuba Circuit",
    "Watkins Glen International – Short Course",
    "Watkins Glen International – Grand Prix",
    "Willow Springs – Big Willow",
    "Willow Springs – Horse Thief Mile",
    "Willow Springs – Kart Track",
    "Willow Springs – Streets of Willow",
    "Willow Springs – Streets of Willow (Reverse)",
    # --- Rally / Dirt ---
    "Colorado Springs – Dirt Track (Short)",
    "Colorado Springs – Dirt Track (Long)",
    "Fishermans Ranch – Dirt Track (Short)",
    "Fishermans Ranch – Dirt Track (Long)",
    "Lake Louise – Road (Short)",
    "Lake Louise – Road (Short Reverse)",
    "Lake Louise – Road (Medium)",
    "Lake Louise – Road (Medium Reverse)",
    "Lake Louise – Road (Long)",
    "Lake Louise – Road (Long+)",
    "Sardegna – Dirt Track A",
    "Sardegna – Dirt Track B",
])


# ---------------------------------------------------------------------------
# Cars by race class  (single source of truth — GT7_CARS is derived below)
# ---------------------------------------------------------------------------
# Gr.1  – top-class prototypes, LMP, historic single-seaters, F-spec
# Gr.2  – Super GT GT500, DTM, Group-A touring car specials
# Gr.3  – GT3 and Gr.3-spec race cars
# Gr.4  – GT4 and Gr.4-spec race cars
# Road Car – production/homologation/track-day road cars
# Other – VGT street concepts, rally/Pikes Peak cars, unclassified specials
GT7_CARS_BY_CATEGORY: dict[str, list[str]] = {
    "Gr.1": [
        "Audi R18 TDI '11",
        "Audi R18 '16",
        "BMW McLaren F1 GTR Race Car '97",
        "Chaparral 2J '70",
        "Chaparral 2X VGT",
        "Dodge SRT Tomahawk VGT (Gr.1)",
        "Dodge SRT Tomahawk X VGT",
        "Ferrari 330 P4 '67",
        "Ferrari 499P Modificata '23",
        "Gran Turismo F1500T-A",
        "Gran Turismo F3500-A",
        "Gran Turismo F3500-B",
        "Hyundai N 2025 VGT (Gr.1)",
        "Jaguar XJR-9 '88",
        "Lamborghini Essenza SCV12 '21",
        "March 701 '70",
        "Maserati 250F '57",
        "Maserati MC12 Versione Corsa '04",
        "Mazda 787B '91",
        "Mazda LM55 VGT (Gr.1)",
        "McLaren F1 GTR - BMW '95",
        "McLaren MP4/4 '88",
        "McLaren VGT (Gr.1)",
        "Mercedes-Benz CLK-LM '98",
        "Mercedes-Benz Sauber C9 '89",
        "Nissan GT-R LM NISMO '15",
        "Nissan R92CP '92",
        "Peugeot 908 HDi FAP '10",
        "Peugeot L750R Hybrid VGT '17",
        "Porsche 917K '70",
        "Porsche 919 Hybrid '16",
        "Porsche 962 C '88",
        "Red Bull X2014 Junior",
        "Red Bull X2014 Standard",
        "Red Bull X2019 Competition",
        "Red Bull X2019 25th Anniversary",
        "Renault Espace F1 '95",
        "Super Formula SF19 Honda '19",
        "Super Formula SF19 Toyota '19",
        "Super Formula SF23 Honda '23",
        "Super Formula SF23 Toyota '23",
        "Toyota GR010 HYBRID '21",
        "Toyota GR010 HYBRID Le Mans Setup '22",
        "Toyota GT-One (TS020) '99",
        "Toyota TS030 Hybrid '12",
        "Toyota TS050 Hybrid '16",
    ],
    "Gr.2": [
        "Alfa Romeo 155 2.5 V6 TI '93",
        "Audi RS 5 Turbo DTM '19",
        "BMW M3 Sport Evolution '89",
        "Honda NSX CONCEPT-GT '16",
        "Honda NSX GT500 '08",
        "Lexus RC F GT500 '16",
        "Lexus SC430 GT500 '08",
        "Mercedes-Benz 190 E 2.5-16 Evolution II '91",
        "Nissan GT-R GT500 '08",
        "Nissan GT-R NISMO GT500 '16",
    ],
    "Gr.3": [
        "Alfa Romeo 4C Gr.3 Race Car",
        "Aston Martin V12 Vantage GT3 '12",
        "Audi R8 LMS Evo '19",
        "BMW M6 GT3 Endurance Model '16",
        "BMW M6 GT3 Sprint Model '16",
        "Chevrolet Corvette (C7) Gr.3",
        "Chevrolet Corvette C8 Gr.3 '22",
        "Citroën GT by Citroën Race Car (Gr.3)",
        "Dodge Viper SRT GT3-R '15",
        "Ferrari 296 GT3 '23",
        "Ferrari 458 Italia GT3 '13",
        "Ford GT Race Car '18",
        "Ford Mustang Gr.3",
        "Lamborghini Huracán GT3 EVO '19",
        "Lamborghini Huracán Super Trofeo EVO2 '21",
        "Mazda RX-Vision GT3 Concept '21",
        "Mazda RX-Vision GT3 Concept Stealth Model",
        "McLaren 650S GT3 '15",
        "Mercedes-AMG GT GT3 '16",
        "Mercedes-AMG GT3 '20",
        "Mercedes-Benz SLS AMG GT3 '11",
        "Porsche 911 RSR '17",
        "Porsche 911 RSR '19",
        "Volkswagen Beetle Gr.3",
    ],
    "Gr.4": [
        "Audi TT Cup '16",
        "Chevrolet Corvette (C7) Gr.4",
        "Ford Mustang Gr.4",
        "Lotus 2-Eleven GT4",
        "Porsche 718 Cayman GT4 Clubsport '16",
    ],
    "Road Car": [
        # Alfa Romeo
        "Alfa Romeo 4C '14",
        "Alfa Romeo 8C Competizione '08",
        "Alfa Romeo GTA '02",
        "Alfa Romeo Giulia TZ2 carrozzata da Zagato '65",
        "Alfa Romeo MiTo '09",
        "Alfa Romeo Spider '10",
        # Alpine
        "Alpine A110 '72",
        "Alpine A110 '17",
        # Amuse
        "Amuse Carbon R",
        "Amuse S2000 GT1 Turbo",
        # Aston Martin
        "Aston Martin DB3S '53",
        "Aston Martin DB5 '64",
        "Aston Martin DB11 '16",
        "Aston Martin DBS Superleggera '18",
        "Aston Martin One-77 '11",
        "Aston Martin V8 Vantage S '15",
        "Aston Martin Valkyrie '21",
        "Aston Martin Vulcan '16",
        # Audi
        "Audi R8 4.2 FSI R tronic '07",
        "Audi Sport quattro '83",
        "Audi TT Coupe 3.2 quattro '03",
        # BMW
        "BMW 3.0 CSL '73",
        "BMW M1 '81",
        "BMW M2 Competition '18",
        "BMW M3 '03",
        "BMW M3 '07",
        "BMW M4 '14",
        "BMW M8 Competition '18",
        "BMW Vision M NEXT '19",
        "BMW Z4 '02",
        "BMW Z8 '00",
        "BMW i8 '14",
        # Bugatti
        "Bugatti Veyron 16.4 '13",
        # Chevrolet
        "Chevrolet Camaro SS '16",
        "Chevrolet Camaro Z28 '69",
        "Chevrolet Corvette C8 '20",
        "Chevrolet Corvette Stingray Convertible (C3) '69",
        "Chevrolet Corvette Z06 '06",
        "Chevrolet Corvette ZR1 '19",
        # Citroën
        "Citroën 2CV '90",
        "Citroën DS 21 Pallas '70",
        # De Tomaso
        "De Tomaso Pantera '71",
        "De Tomaso Pantera '92",
        # Dodge
        "Dodge Challenger R/T '70",
        "Dodge Challenger SRT Hellcat '15",
        "Dodge Charger R/T 426 Hemi '68",
        "Dodge Viper GTS '02",
        # Ferrari
        "Ferrari 250 GTO '62",
        "Ferrari 308 GTB '75",
        "Ferrari 365 GTB4 '71",
        "Ferrari 458 Italia '09",
        "Ferrari 512 BB '76",
        "Ferrari 599XX '10",
        "Ferrari 612 Scaglietti '04",
        "Ferrari 812 Superfast '17",
        "Ferrari 812 Competizione '21",
        "Ferrari California T '14",
        "Ferrari Enzo Ferrari '02",
        "Ferrari F12berlinetta '12",
        "Ferrari F40 '92",
        "Ferrari F50 '95",
        "Ferrari F8 Tributo '19",
        "Ferrari FXX K '14",
        "Ferrari GTO '84",
        "Ferrari LaFerrari '13",
        "Ferrari Roma '20",
        "Ferrari SF90 Stradale '19",
        # Ford
        "Ford Escort RS Cosworth '92",
        "Ford Focus ST '06",
        "Ford GT '06",
        "Ford GT '17",
        "Ford GT40 Mark I '66",
        "Ford Mustang (1st Gen) '62",
        "Ford Mustang Boss 429 '69",
        "Ford Sierra RS Cosworth '87",
        "Ford Shelby GT350R '16",
        "Ford Shelby GT500 '07",
        # Genesis
        "Genesis G70 Shooting Brake '21",
        # Honda
        "Honda Beat '91",
        "Honda City Turbo II '83",
        "Honda Civic (EG) SiR-II '93",
        "Honda Civic Type R (EK) '97",
        "Honda Civic Type R (FK8) '17",
        "Honda Fit RS '09",
        "Honda NSX '91",
        "Honda NSX '17",
        "Honda NSX-R '02",
        "Honda S2000 '99",
        "Honda S660 '15",
        "Honda S800 '66",
        # Hyundai
        "Hyundai Elantra N '21",
        "Hyundai Genesis Coupe 3.8 Track '13",
        "Hyundai IONIQ 5 N '23",
        # Jaguar
        "Jaguar E-type Coupe '61",
        "Jaguar XJ13 '66",
        # KTM
        "KTM X-Bow GT '11",
        # Lamborghini
        "Lamborghini Aventador LP 700-4 '11",
        "Lamborghini Aventador LP 700-4 Pirelli Edition '13",
        "Lamborghini Aventador SV '15",
        "Lamborghini Countach 25th Anniversary '88",
        "Lamborghini Countach LP400 '74",
        "Lamborghini Countach LPI 800-4 '22",
        "Lamborghini Diablo GT '00",
        "Lamborghini Diablo SV '01",
        "Lamborghini Gallardo LP 560-4 '08",
        "Lamborghini Huracán LP 610-4 '15",
        "Lamborghini Miura P400 '66",
        "Lamborghini Murciélago LP 670-4 SuperVeloce '10",
        "Lamborghini Sian Roadster '20",
        "Lamborghini Urus '18",
        # Lancia
        "Lancia Delta HF Integrale '92",
        "Lancia Fulvia 1.3 S '72",
        "Lancia Stratos '73",
        # Lexus
        "Lexus LC500 '17",
        "Lexus LFA '10",
        "Lexus RC F '14",
        # Lotus
        "Lotus Elise Cup 250 '17",
        "Lotus Evija '19",
        "Lotus Exige S '12",
        "Lotus Exige Sprint 360 '17",
        # Maserati
        "Maserati A6GCS/53 '54",
        "Maserati GranTurismo S '08",
        # Mazda
        "Mazda 3 XD Touring '19",
        "Mazda Atenza Sedan XD L Package '15",
        "Mazda Eunos Roadster (NA) '89",
        "Mazda MX-5 (NC) 2.0 '05",
        "Mazda MX-5 Miata '98",
        "Mazda RX-7 FD3S GT-X '97",
        "Mazda RX-7 FC3S Type II '89",
        "Mazda RX-7 Type RZ '99",
        "Mazda RX500 '70",
        # McLaren
        "McLaren 720S '17",
        "McLaren F1 '94",
        "McLaren MP4-12C '10",
        "McLaren P1 GTR '16",
        "McLaren Senna '18",
        # Mercedes-Benz
        "Mercedes-AMG A 45 S '21",
        "Mercedes-AMG C 63 S Coupé '15",
        "Mercedes-AMG GT Black Series '21",
        "Mercedes-AMG GT R '19",
        "Mercedes-AMG SLS AMG '11",
        "Mercedes-Benz 300 SL '54",
        "Mercedes-Benz SLR McLaren '09",
        # Mini
        "Mini Cooper '65",
        "Mini Cooper S '05",
        # Mitsubishi
        "Mitsubishi 3000GT VR-4 '98",
        "Mitsubishi FTO GP Version R '97",
        "Mitsubishi GTO Twin Turbo '94",
        "Mitsubishi Lancer Evo Final Edition '15",
        "Mitsubishi Lancer Evolution III GSR '95",
        "Mitsubishi Lancer Evolution IV GSR '96",
        "Mitsubishi Lancer Evolution VI T.M. Edition '99",
        "Mitsubishi Lancer Evolution IX GSR '05",
        "Mitsubishi Lancer Evolution X GSR P Package '07",
        # Nissan
        "Nissan Fairlady Z (S30) '78",
        "Nissan Fairlady Z (Z33) Version ST '07",
        "Nissan GT-R NISMO '17",
        "Nissan GT-R Premium Edition T-spec '24",
        "Nissan Silvia K's (S13) '88",
        "Nissan Silvia K's Dia Selection (S14) '96",
        "Nissan Silvia Spec-R Aero (S15) '02",
        "Nissan Skyline GT-R (R32) '89",
        "Nissan Skyline GT-R (R33) '97",
        "Nissan Skyline GT-R (R34) V-spec II Nür '02",
        "Nissan Z '23",
        # Opel
        "Opel Kadett C GT/E '77",
        # Pagani
        "Pagani Huayra '13",
        "Pagani Huayra BC '16",
        "Pagani Zonda C12F Coupe '04",
        "Pagani Zonda R '09",
        # Peugeot
        "Peugeot 205 GTI '84",
        "Peugeot 208 GTi by Peugeot Sport '14",
        "Peugeot RCZ '10",
        # Pontiac
        "Pontiac Firebird Trans Am '78",
        "Pontiac GTO '65",
        # Porsche
        "Porsche 356 A/1500 GS Carrera Speedster '56",
        "Porsche 718 Cayman GT4 '20",
        "Porsche 718 Cayman GT4 RS '21",
        "Porsche 911 (930) Turbo 3.3 '81",
        "Porsche 911 (964) Carrera RS '92",
        "Porsche 911 (993) Carrera RS '95",
        "Porsche 911 (997) GT3 '09",
        "Porsche 911 (997) GT3 RS '09",
        "Porsche 911 Carrera RS 2.7 '73",
        "Porsche 911 GT3 '19",
        "Porsche 911 GT3 RS '22",
        "Porsche 911 Targa 4S '20",
        "Porsche 911 Turbo '81",
        "Porsche 918 Spyder '13",
        "Porsche Mission X '23",
        "Porsche Panamera Turbo S '16",
        "Porsche Taycan Turbo S '19",
        # Renault
        "Renault Clio R.S. Phase 1 220 Trophy '15",
        "Renault Clio V6 24V '03",
        "Renault R8 Gordini '66",
        # Shelby
        "Shelby Cobra 427 '66",
        "Shelby Cobra Daytona Coupe '64",
        # Subaru
        "Subaru BRZ S '21",
        "Subaru Impreza 22B-STi '98",
        "Subaru Impreza WRX STi '04",
        "Subaru Impreza WRX STi '09",
        # Suzuki
        "Suzuki Swift Sport '07",
        # Toyota
        "Toyota 2000GT '67",
        "Toyota 86 GT '15",
        "Toyota 86 GR Sport '19",
        "Toyota Aqua S '11",
        "Toyota Celica GT-FOUR (ST205) '94",
        "Toyota Corolla Levin (AE86) 1600GT APEX '83",
        "Toyota GR Supra '19",
        "Toyota GR Supra Racing Concept '18",
        "Toyota GR Yaris '20",
        "Toyota GR86 '21",
        "Toyota MR2 1600 '86",
        "Toyota MR2 GT-S '97",
        "Toyota Prius G '09",
        "Toyota Supra 3.0GT Turbo A '88",
        "Toyota Supra RZ '97",
        # TVR
        "TVR Tuscan Speed 6 '00",
        # Volkswagen
        "Volkswagen Beetle '63",
        "Volkswagen Golf I GTI '83",
        "Volkswagen Golf IV GTI '97",
        "Volkswagen Golf GTE '14",
        "Volkswagen Golf GTI Clubsport '16",
        "Volkswagen Golf VII GTI '14",
        "Volkswagen Golf VIII R '22",
        "Volkswagen Phaeton V12 TDI '08",
        "Volkswagen Polo Mk1 GTI '83",
        "Volkswagen Scirocco '09",
        # Volvo
        "Volvo 240 Estate '87",
        "Volvo P1800 '63",
    ],
    "Other": [
        # VGT street concepts
        "Alpine A110 VGT",
        "Audi VGT",
        "Audi e-tron VGT",
        "Bugatti VGT",
        "Chevrolet Corvette CX Concept '25",
        "Chevrolet Corvette CX.R VGT Concept",
        "Citroën GT by Citroën '08",
        "Dodge SRT Tomahawk GTS-R VGT",
        "Dodge SRT Tomahawk S VGT",
        "Ferrari VGT",
        "Genesis X Gran Berlinetta VGT Concept",
        "Genesis X Gran Racer VGT Concept",
        "Honda Project 2&4 '15",
        "Hyundai N 2025 VGT",
        "Italdesign VGT Off-road Mode",
        "Italdesign VGT Street Mode",
        "Jaguar Vision GT Coupé",
        "Jaguar Vision GT Roadster",
        "Jaguar Vision GT SV",
        "Lamborghini Lambo V12 VGT",
        "Lexus LF-LC GT VGT",
        "Mazda LM55 VGT",
        "McLaren VGT",
        "Mitsubishi Eclipse Concept-E",
        "Opel Corsa GSE VGT",
        "Peugeot VGT",
        "Porsche 917 LIVING LEGEND",
        "Porsche VGT",
        "Porsche VGT Spyder",
        "Škoda VGT",
        "Toyota FT-1 VGT",
        # Classic race cars (no modern Gr. class)
        "Alpine A220 Race Car '68",
        # Rally / Pikes Peak / off-road
        "Audi Sport quattro S1 Pikes Peak '87",
        "Citroën C4 WRC '08",
        "Citroën Xsara Rally Car",
        "Lancia Rally 037 Rally Car '82",
        "Lotus Exige R-GT '12",
        "Nissan Leaf Nismo RC '18",
        "Renault Sport Mégane Trophy V6 '11",
        "Suzuki V6 Escudo Pikes Peak Special '98",
        "Toyota Celica GT-FOUR Rally Car (ST185) '93",
        "Toyota Land Cruiser 40 '78",
        "Volkswagen ID.R '19",
        "Volkswagen Race Touareg 3 '11",
    ],
}

# Flat alphabetically-sorted list for backward compatibility and AI prompts.
GT7_CARS: list[str] = sorted(
    car for cars in GT7_CARS_BY_CATEGORY.values() for car in cars
)


# ---------------------------------------------------------------------------
# Track disambiguation hints
# ---------------------------------------------------------------------------
# Shown in the track dropdown alongside the canonical name.
# Keys must exactly match entries in GT7_TRACKS.
# Only tracks that benefit from extra context are listed here.
GT7_TRACK_INFO: dict[str, str] = {
    # Fuji
    "Fuji Speedway":                                        "~4.6 km • full F1 layout, long main straight",
    "Fuji Speedway – Short":                                "~3.7 km • shorter alternative layout",
    # Nürburgring — very different lengths, easy to pick the wrong one
    "Nürburgring – Nordschleife":                           "~20.8 km • 73 turns — full Green Hell",
    "Nürburgring – Nordschleife (24h Configuration)":       "~25.4 km • extra Döttinger section",
    "Nürburgring – Nordschleife (Industriefahrten)":        "~20.8 km • Nordschleife, open-lap format",
    "Nürburgring – Grand Prix":                             "~5.1 km • modern GP loop",
    "Nürburgring – GP Sprint Short":                        "~3.6 km • shortened GP variant",
    "Nürburgring – Sprint Short":                           "~2.5 km • tightest Nürburgring layout",
    # Circuit de la Sarthe — chicane distinction matters for lap times
    "Circuit de la Sarthe":                                 "~13.6 km • Le Mans with Ford / Porsche chicanes",
    "Circuit de la Sarthe (No Chicane)":                    "~13.6 km • Le Mans, no chicanes, much faster",
    # Autodromo Lago Maggiore — 6 layouts, very different lengths
    "Autodromo Lago Maggiore – Full Course":                "~5.9 km • complete outer layout",
    "Autodromo Lago Maggiore – West":                       "~4.6 km • western section",
    "Autodromo Lago Maggiore – Center":                     "~2.8 km",
    "Autodromo Lago Maggiore – Porsche Cup":                "~3.5 km",
    "Autodromo Lago Maggiore – East Short":                 "~1.8 km • shortest layout",
    "Autodromo Lago Maggiore – South":                      "~3.1 km",
    # Willow Springs — kart track is easy to select by accident
    "Willow Springs – Big Willow":                          "~4.0 km • full high-speed circuit",
    "Willow Springs – Horse Thief Mile":                    "~1.6 km • tight twisty inner loop",
    "Willow Springs – Kart Track":                          "~0.8 km • very short karting layout",
    "Willow Springs – Streets of Willow":                   "~2.4 km • street-style section",
    # Blue Moon Bay — oval vs road course
    "Blue Moon Bay Speedway":                               "~4.0 km • high-speed oval",
    "Blue Moon Bay Speedway – Infield A":                   "~3.2 km • infield road course A",
    "Blue Moon Bay Speedway – Infield B":                   "~3.0 km • infield road course B",
    # Brands Hatch — very different lengths
    "Brands Hatch – Indy Circuit":                          "~1.9 km • short club circuit",
    "Brands Hatch – Grand Prix Circuit":                    "~3.9 km • full GP layout (Druids to Clark)",
    # Monza
    "Autodromo Nazionale Monza":                            "~5.8 km • full F1 circuit, high-speed",
    "Autodromo Nazionale Monza – Junior Circuit":           "~2.4 km • inner shorter layout",
    # Barcelona
    "Barcelona – Circuit de Catalunya":                     "~4.7 km • full F1 circuit",
    "Barcelona – Circuit de Catalunya – Club Circuit":      "~2.9 km • club/shorter layout",
    "Barcelona – Rallycross Circuit":                       "~1.0 km • mixed dirt/tarmac",
    # Suzuka — East course is very different to the full figure-8
    "Suzuka Circuit":                                       "~5.8 km • full figure-8 layout",
    "Suzuka Circuit – East Course":                         "~2.2 km • eastern section only, no bridge",
    # Red Bull Ring
    "Red Bull Ring – Grand Prix":                           "~4.3 km • full Austrian GP layout",
    "Red Bull Ring – Short":                                "~2.3 km • compact inner loop",
    # Watkins Glen
    "Watkins Glen International – Grand Prix":              "~5.4 km • full circuit including The Boot",
    "Watkins Glen International – Short Course":            "~3.4 km • inner shorter loop",
    # Autopolis
    "Autopolis – International Racing Course":              "~4.7 km • full layout",
    "Autopolis – Short Course":                             "~2.3 km • shorter variant",
    # Daytona — road vs oval, very different character
    "Daytona – Road Course":                                "~5.7 km • infield + banked oval section",
    "Daytona – Tri-Oval":                                   "~4.0 km • pure banked oval",
    # Special Stage X — easy to accidentally pick for a normal race
    "Special Stage Route X":                                "~30 km • ultra-long endurance straight",
    # Alsace
    "Alsace – Village":                                     "~3.5 km • village roads, longer loop",
    "Alsace – Village Short":                               "~2.1 km • compact village section",
    # Dragon Trail
    "Dragon Trail – Seaside":                               "~4.4 km • fast coastal cliff road",
    "Dragon Trail – Gardens":                               "~3.6 km • botanical garden setting",
    # Tokyo Expressway — inner vs outer direction confusable
    "Tokyo Expressway – Central Outer Loop":                "~3.5 km • outer ring, counterclockwise",
    "Tokyo Expressway – Central Inner Loop":                "~3.5 km • inner ring, clockwise",
    "Tokyo Expressway – South Outer Loop":                  "~3.0 km • south outer",
    "Tokyo Expressway – South Inner Loop":                  "~3.0 km • south inner",
    # Northern Isle — oval, not immediately obvious from name
    "Northern Isle Speedway":                               "~4.0 km • high-speed oval",
    # Kyoto Driving Park
    "Kyoto Driving Park – Yamagiwa":                        "~3.0 km",
    "Kyoto Driving Park – Yamagiwa+Miyabi":                 "~4.7 km • longest Kyoto layout",
    "Kyoto Driving Park – Miyabi":                          "~2.5 km",
    # Sainte-Croix
    "Sainte-Croix – Circuit A":                             "~3.2 km",
    "Sainte-Croix – Circuit B":                             "~4.1 km • longest Sainte-Croix variant",
    "Sainte-Croix – Circuit C":                             "~2.5 km • shortest variant",
    # Spa
    "Spa-Francorchamps":                                    "~7.0 km • Eau Rouge / Raidillon, Belgian GP",
    # Bathurst
    "Bathurst – Mount Panorama Motor Racing Circuit":        "~6.2 km • famous mountain section (The Dipper)",
    # Laguna Seca
    "Laguna Seca – WeatherTech Raceway":                    "~3.6 km • famous Corkscrew corner",
    # High-Speed Ring — fictional, high-speed nature not obvious
    "High-Speed Ring":                                      "~3.2 km • smooth high-speed fictional circuit",
    # Eiger
    "Eiger Nordwand – Short Track":                         "short tarmac/dirt mix at foot of Eiger",
    "Eiger Nordwand – G Trail":                             "longer off-road route through Eiger valley",
}


# ---------------------------------------------------------------------------
# Tyre temperature presets (delegated to data/tyres.py — single source of truth)
# ---------------------------------------------------------------------------

# Keyed by canonical compound name ("Racing Soft", "Sports Medium", etc.).
# Backward-compat alias keys for old lookup strings are added below.
TYRE_TEMP_PRESETS: dict[str, dict[str, float]] = {
    c.name: {
        "cold_max":    float(c.cold_max),
        "warming_max": float(c.warming_max),
        "optimal_max": float(c.optimal_max),
        "hot_max":     float(c.hot_max),
    }
    for c in ALL_COMPOUNDS
}
# Old parenthetical-style keys that existing callers may look up
TYRE_TEMP_PRESETS["Racing Soft (RS)"]   = TYRE_TEMP_PRESETS["Racing Soft"]
TYRE_TEMP_PRESETS["Racing Medium (RM)"] = TYRE_TEMP_PRESETS["Racing Medium"]
TYRE_TEMP_PRESETS["Racing Hard (RH)"]   = TYRE_TEMP_PRESETS["Racing Hard"]
TYRE_TEMP_PRESETS["Intermediate (IM)"]  = TYRE_TEMP_PRESETS["Intermediate"]
TYRE_TEMP_PRESETS["Wet (W)"]            = TYRE_TEMP_PRESETS["Heavy Wet"]


def normalise_compound(compound: str) -> str | None:
    """Return the canonical compound display name for any input string, or None."""
    code = normalise_code(compound)
    tc = get_by_code(code) if code else None
    return tc.name if tc else None


def build_track_context(track_name: str) -> str:
    """Return an enriched track string for AI prompts.

    Appends the GT7_TRACK_INFO hint (length + character) when available so the
    AI knows whether it's building a setup for a 20 km endurance circuit or a
    1.9 km club circuit.
    """
    if not track_name:
        return "Track: Unknown"
    info = GT7_TRACK_INFO.get(track_name, "")
    if info:
        return f"Track: {track_name}  ({info})"
    return f"Track: {track_name}"


_EXTRA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "gt7_extra.json")


def reload_extra() -> None:
    """Merge data/gt7_extra.json into GT7_CARS_BY_CATEGORY, GT7_CARS, and GT7_TRACKS.

    Safe to call multiple times — duplicates are silently skipped.
    """
    global GT7_CARS_BY_CATEGORY, GT7_CARS, GT7_TRACKS
    try:
        raw = open(_EXTRA_PATH, encoding="utf-8").read()
        extra = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    for cat, cars in extra.get("cars", {}).items():
        if cat not in GT7_CARS_BY_CATEGORY:
            GT7_CARS_BY_CATEGORY[cat] = []
        for car in cars:
            if car and car not in GT7_CARS_BY_CATEGORY[cat]:
                GT7_CARS_BY_CATEGORY[cat].append(car)
    GT7_CARS = sorted(c for cats in GT7_CARS_BY_CATEGORY.values() for c in cats)
    for track in extra.get("tracks", []):
        if track and track not in GT7_TRACKS:
            GT7_TRACKS.append(track)
    GT7_TRACKS.sort()

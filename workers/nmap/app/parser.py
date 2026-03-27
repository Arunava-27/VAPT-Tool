import xml.etree.ElementTree as ET

def parse_nmap_xml(xml_data: str):
    root = ET.fromstring(xml_data)

    results = []

    for host in root.findall("host"):
        address = host.find("address")
        ip = address.get("addr") if address is not None else "unknown"

        ports = []

        for port in host.findall(".//port"):
            state = port.find("state").get("state")

            if state == "open":
                service = port.find("service")
                ports.append({
                    "port": int(port.get("portid")),
                    "protocol": port.get("protocol"),
                    "service": service.get("name") if service is not None else "unknown"
                })

        results.append({
            "host": ip,
            "open_ports": ports
        })

    return results
# Emit semantic Stage4 capture classes from numeric IPv4 tcpdump lines.
function endpoint_ip(endpoint,    n, fields, i, result) {
	n = split(endpoint, fields, /\./)
	if (n < 2) return ""
	result = fields[1]
	for (i = 2; i < n; i++) result = result "." fields[i]
	return result
}

function endpoint_port(endpoint,    n, fields) {
	n = split(endpoint, fields, /\./)
	return (n >= 2) ? fields[n] : ""
}

function numeric_port(value) {
	return value ~ /^[0-9]+$/
}

{
	ip_field = 0
	for (i = 1; i <= NF; i++) {
		if ($i == "IP") {
			ip_field = i
			break
		}
	}
	if (!ip_field || NF < ip_field + 3) next

	src = $(ip_field + 1)
	dst = $(ip_field + 3)
	sub(/:$/, "", dst)
	if (!match($0, /Flags \[[^]]*\]/)) next

	flags = $0
	sub(/^.*Flags \[/, "", flags)
	sub(/\].*$/, "", flags)
	src_ip = endpoint_ip(src)
	src_port = endpoint_port(src)
	dst_ip = endpoint_ip(dst)
	dst_port = endpoint_port(dst)

	host_to_device = src_ip == host && dst_ip == device && dst_port == port && numeric_port(src_port)
	device_to_host = src_ip == device && src_port == port && dst_ip == host && numeric_port(dst_port)

	if (host_to_device && index(flags, "S") && !index(flags, ".")) print "SYN"
	if (device_to_host && index(flags, "S") && index(flags, ".")) print "SYNACK"
	if ((host_to_device || device_to_host) && $0 ~ /length [1-9][0-9]*:/) print "HTTP_DATA"
	if (host_to_device && index($0, "GET / HTTP/1.1")) print "HTTP_GET"
	if (device_to_host && index($0, "HTTP/1.1 200 OK")) print "HTTP_200"
}

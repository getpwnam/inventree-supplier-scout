#!/bin/sh
TOKEN=$1
BASE='https://inventree.ebnx.net'
#BASE='https://172.17.132.98' #with -k if needed

call_api() {
	label=$1
	path=$2

	echo "== ${label} =="

	body_file=$(mktemp)
	err_file=$(mktemp)

	if [ "${INSECURE:-0}" = "1" ]; then
		curl_code=$(curl -k -sS -H "Authorization: Token $TOKEN" -H "Accept: application/json" -o "$body_file" -w '%{http_code}' "$BASE$path" 2>"$err_file")
	else
		curl_code=$(curl -sS -H "Authorization: Token $TOKEN" -H "Accept: application/json" -o "$body_file" -w '%{http_code}' "$BASE$path" 2>"$err_file")
	fi
	curl_exit=$?

	if [ "$curl_exit" -ne 0 ]; then
		echo "curl_error: $(cat "$err_file")"
	else
		echo "http_status: $curl_code"
	fi

	echo "response_body:"
	cat "$body_file"
	echo

	rm -f "$body_file" "$err_file"
}

call_api "primary_action by target_model/target_id" "/api/plugins/ui/features/primary_action/?target_model=part&target_id=221"
call_api "primary_action by location" "/api/plugins/ui/features/primary_action/?location=/part/221/"
call_api "part detail" "/api/part/221/"
call_api "SupplierScout token debug" "/plugin/supplierscout/tokendebug.json?pk=221"
call_api "SupplierScout user settings" "/api/plugins/supplierscout/user-settings/"
call_api "SupplierScout global settings" "/api/plugins/supplierscout/settings/"
call_api "ENABLE_PLUGINS_INTERFACE" "/api/settings/global/ENABLE_PLUGINS_INTERFACE/"
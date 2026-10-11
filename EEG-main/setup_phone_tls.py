"""Create a local CA and a server certificate. Does not install trust automatically."""
import argparse, datetime, ipaddress
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
p=argparse.ArgumentParser();p.add_argument('--host',required=True);a=p.parse_args();ip=ipaddress.ip_address(a.host)
folder=Path(__file__).resolve().parent/'.phone';folder.mkdir(mode=0o700,exist_ok=True)
if (folder/'ca-key.pem').exists():raise SystemExit('Certificates already exist. Keep the existing CA; do not overwrite trusted keys automatically.')
now=datetime.datetime.now(datetime.timezone.utc)
ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Brain Gremlin Local Phone CA')])
ca=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(days=365)).add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True).sign(ca_key,hashes.SHA256())
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
cert=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,a.host)])).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(days=90)).add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False).add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip)]),critical=False).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).sign(ca_key,hashes.SHA256())
for filename,k in [('ca-key.pem',ca_key),('server-key.pem',key)]:
 path=folder/filename;path.write_bytes(k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));path.chmod(0o600)
(folder/'ca.cer').write_bytes(ca.public_bytes(serialization.Encoding.DER));(folder/'server.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
print('Public certificate to trust on Mac/iPhone:',folder/'ca.cer')
print('SHA256 fingerprint:',ca.fingerprint(hashes.SHA256()).hex(':'))

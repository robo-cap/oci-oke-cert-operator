import base64
import oci
import requests

from kopf import TemporaryError, PermanentError


def get_cluster_ocid(logger, **kwargs):

    logger.debug("Attempting to fetch OKE cluster OCID using instance metadata.")
    
    try:
        response = requests.get(
            "http://169.254.169.254/opc/v2/instance/metadata/", 
            headers={"Authorization": "Bearer Oracle"}, 
            timeout=5)
    
        if response.status_code != 200:
            logger.warn(f"Unexpected response code received when attempting to fetch instance metadata: {response.status_code}. Response text: {response.text}.")
            return None
    
        cluster_id = response.json().get("oke-cluster-id")
        logger.debug(f"Successfuly fetched OKE cluster OCID: {cluster_id}.")
    
    except Exception as e:
        logger.warn(f"An unexpected error occured during attempt to fetch cluster OCID: {e}.")
        return None
    
    return cluster_id


def get_compartment_ocid(cluster_id, logger, **kwargs):

    logger.debug("Attempting to fetch OKE compartment OCID using cluster OCID.")

    try:

        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    
    except Exception as e:
        raise PermanentError("Failed to get Instance Principal Signer")

    try:
        container_engine_client = oci.container_engine.ContainerEngineClient(
            {},
            signer=signer,
            timeout=5)
        get_cluster_response = container_engine_client.get_cluster(
            cluster_id=cluster_id,
            )
        
        if get_cluster_response.status != 200:
            logger.warn(f"Unexpected response code received when attempting to fetch cluster {cluster_id} information: {get_cluster_response.status}. Response text: {get_cluster_response.data}.")
            return None

        compartment_id = get_cluster_response.data.compartment_id
        logger.debug(f"Successfuly fetched OKE cluster {cluster_id} compartment OCID: {compartment_id}")

    except Exception as e:
        logger.warn(f"An unexpected error occured during attempt to fetch cluster {cluster_id} compartment_id: {e}.")
        return None

    return compartment_id


def get_certificate_slots_from_pem(pem_data):

    start_line = '-----BEGIN CERTIFICATE-----'
    result = []

    cert_slots = pem_data.split(start_line)
    
    for single_pem_cert in cert_slots[1:]:
        cert = start_line+single_pem_cert
        result.append(cert)
    
    return result


def create_certificate(compartment_id, secret_name, tls_crt, tls_key, logger, **kwargs):

    logger.debug(f"Attempting to create new certificate in compartment {compartment_id}.")

    try:
    
        logger.debug("Attempting to fetch certificate slots from tls_crt.")
        cert_slots = get_certificate_slots_from_pem(base64.b64decode(tls_crt).decode("utf-8"))
    
        if len(cert_slots) < 2:
            logger.error("Failed to extract PEM certificate and intermediate certificates from tls.crt file.")
            raise Exception("Failed to extract PEM certificate and intermediate certificates from tls.crt file.")

    except Exception as e:
        raise PermanentError(e)
    
    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    except Exception as e:
        raise PermanentError("Failed to get Instance Principal Signer")
    
    try:
        certificates_management_client = oci.certificates_management.CertificatesManagementClient(
            {},
            signer=signer,
            timeout=5)

        create_certificate_response = certificates_management_client.create_certificate(
            create_certificate_details=oci.certificates_management.models.CreateCertificateDetails(
                name=secret_name,
                compartment_id=compartment_id,
                certificate_config=oci.certificates_management.models.CreateCertificateByImportingConfigDetails(
                    config_type="IMPORTED",
                    certificate_pem=cert_slots[0],
                    cert_chain_pem="\n".join(cert_slots[1:]),
                    private_key_pem=base64.b64decode(tls_key).decode("utf-8")),
                description=secret_name,
                freeform_tags={
                    'managed_by': 'oke_operator'}))
        
        if create_certificate_response.status != 200:
            logger.warn(f"Unexpected response code received when attempting to create OCI certificate with name {secret_name} : {create_certificate_response.status}. Response text: {create_certificate_response.data}.")
            return None
        
        certificate_id = create_certificate_response.data.id
        logger.debug(f"Successfuly created certificate {secret_name}, {certificate_id} in compartment: {compartment_id}")
    
    except Exception as e:
        logger.warn(f"An unexpected error occured during attempt to create certificate {secret_name} in compartment {compartment_id}: {e}.")
        return None
    
    return certificate_id


def update_certificate(certificate_id, tls_crt, tls_key, logger, **kwargs):

    logger.debug(f"Attempting to update certificate {certificate_id}.")

    try:

        logger.debug("Attempting to fetch certificate slots from tls_crt.")
        cert_slots = get_certificate_slots_from_pem(base64.b64decode(tls_crt).decode("utf-8"))
    
        if len(cert_slots) < 2:
            logger.warn("Failed to extract certificate.PEM and intermediate certificates from tls.crt file.")
            raise Exception("Failed to extract certificate.PEM and intermediate certificates from tls.crt file.")

    except Exception as e:
        raise PermanentError(e)
    
    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    except Exception as e:
        raise PermanentError("Failed to get Instance Principal Signer")
    
    try:
        certificates_management_client = oci.certificates_management.CertificatesManagementClient(
            {},
            signer=signer,
            timeout=5)

        update_certificate_response = certificates_management_client.update_certificate(
            certificate_id=certificate_id,
            update_certificate_details=oci.certificates_management.models.UpdateCertificateDetails(
                certificate_config=oci.certificates_management.models.UpdateCertificateByImportingConfigDetails(
                    config_type="IMPORTED",
                    certificate_pem=cert_slots[0],
                    cert_chain_pem="\n".join(cert_slots[1:]),
                    private_key_pem=base64.b64decode(tls_key).decode("utf-8"))))

        if update_certificate_response.status != 200:
            logger.warn(f"Unexpected response code received when attempting to update OCI certificate {certificate_id} : {update_certificate_response.status}. Response text: {update_certificate_response.data}.")
            return None
        
        logger.debug(f"Successfuly updated certificate {certificate_id}")

        certificate_version = update_certificate_response.data.current_version.version_number

    except Exception as e:
        logger.warn(f"An unexpected error occured during attempt to update certificate {certificate_id}: {e}.")
        return None
    
    return certificate_version


def schedule_certificate_deletion(certificate_id, logger, **kwargs):

    logger.debug(f"Attempting to schedule certificate deletion {certificate_id}.")

    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    except Exception as e:
        raise PermanentError("Failed to get Instance Principal Signer")
    
    try:
        
        certificates_management_client = oci.certificates_management.CertificatesManagementClient(
            {},
            signer=signer,
            timeout=5)

        schedule_delete_certificate_response = certificates_management_client.schedule_certificate_deletion(
            certificate_id=certificate_id,
            schedule_certificate_deletion_details=oci.certificates_management.models.ScheduleCertificateDeletionDetails()
            )

        if schedule_delete_certificate_response.status != 200:
            logger.warn(f"Unexpected response code received when attempting to schedule certificate {certificate_id} deletion: {schedule_delete_certificate_response.status}. Response text: {schedule_delete_certificate_response.data}.")
            return None
        
        logger.debug(f"Successfuly schedule certificate {certificate_id} for deletion.")

    except Exception as e:
        logger.warn(f"An unexpected error occured during attempt to schedule certificate {certificate_id} deletion: {e}.")
        return None
    
    return True
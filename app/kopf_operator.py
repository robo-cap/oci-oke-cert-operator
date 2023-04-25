import os

import kopf

from utils import get_cluster_ocid, get_compartment_ocid, create_certificate, update_certificate, schedule_certificate_deletion


COMPARTMENT_OCID = None

## Used for local test
# @kopf.on.login()
# def login_fn(**kwargs):
#     return kopf.login_via_client(**kwargs)


@kopf.on.startup(errors=kopf.ErrorsMode.PERMANENT)
def configure(settings: kopf.OperatorSettings, logger, **_):
    global COMPARTMENT_OCID

    if os.environ.get("COMPARTMENT_OCID", None) != None:
    
        COMPARTMENT_OCID = os.environ.get("COMPARTMENT_OCID")
    
    else:
    
        logger.info("COMPARTMENT_OCID environment variable is not set. Attempting to determine it using instance metadata.")
    
        cluster_ocid = get_cluster_ocid(logger)

        if cluster_ocid != None:
            compartment_id = get_compartment_ocid(cluster_ocid, logger)
        else:
            logger.error("Failed to fetch cluster_ocid")
            raise kopf.PermanentError
        
        if compartment_id != None:
            COMPARTMENT_OCID = compartment_id
        else:
            logger.error("Failed to fetch compartment_ocid.")
            raise kopf.PermanentError

    settings.peering.standalone = True
    # settings.posting.level = logging.ERROR
    settings.execution.max_workers = 20

    # settings.watching.server_timeout = 90
    # settings.watching.connect_timeout = 90
    
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage()
    settings.persistence.diffbase_storage = kopf.AnnotationsDiffBaseStorage(
        prefix='kopf.zalando.org',
        key='last-handled-configuration',
    )



@kopf.on.create("Secret", field='data', value=kopf.PRESENT, labels={'sync-to-oci': 'yes'}, retries=3)
def create_oci_certificate(body, name, uid, namespace, status, logger, patch, **kwargs):

    try:
        tls_crt = body.get('data', {}).get("tls.crt")
        tls_key = body.get('data', {}).get("tls.key")
    
    except KeyError:
        logger.error(f"Make sure tls.crt and tls.key keys are present for secret {namespace}/{name}.")
        raise kopf.PermanentError(f"Make sure tls.crt and tls.key keys are present for secret {namespace}/{name}.")
    
    try:
        certificate_ocid = create_certificate(
            compartment_id=COMPARTMENT_OCID, 
            secret_name=f"{namespace}_{name}_{uid}", 
            tls_crt=tls_crt, 
            tls_key=tls_key,
            logger=logger)
        if certificate_ocid != None:
            patch.metadata.annotations["oci.oraclecloud.com/certificate-id"] = certificate_ocid
            logger.info(f"OCICertificateCreated | OCI Certificate {certificate_ocid} successfuly created.")
        else:
            raise kopf.TemporaryError("Could not create OCI certificate using secret data. Retrying...", delay=60)
    except Exception as e:
        logger.error(f"OCICertificateCreationFail | {e}")
    



@kopf.on.update("Secret", field='data', labels={'sync-to-oci': 'yes'}, retries=3)
def update_oci_certificate(body, spec, old, new, name, uid, namespace, logger, patch, **kwargs):

    oci_certificate_id = body.metadata.annotations.get("oci.oraclecloud.com/certificate-id", None)

    if oci_certificate_id != None:
        
        try:
            tls_crt = body.get('data', {}).get("tls.crt")
            tls_key = body.get('data', {}).get("tls.key")
        
        except KeyError:
            logger.error(f"Make sure tls.crt and tls.key keys are present for secret {namespace}/{name}.")
            raise kopf.PermanentError
        
        try:
            certificate_version = update_certificate(
                certificate_id=oci_certificate_id, 
                tls_crt=tls_crt, 
                tls_key=tls_key,
                logger=logger)
            if certificate_version != None:
                logger.info(f"OCICerificateUpdated | OCI Certificate {oci_certificate_id} current version was updated to {certificate_version}.")
            else:
                raise kopf.TemporaryError("Could not update OCI certificate. Retrying...", delay=60)
        
        except kopf.TemporaryError:
            raise
        except Exception as e:
            logger.error(f"OCICertificateUpdateFail | {e}")
            raise kopf.PermanentError(f"OCICertificateUpdateFail | {e}")

    else:

        try:
            tls_crt = body.get('data', {}).get("tls.crt")
            tls_key = body.get('data', {}).get("tls.key")
        
        except KeyError:
            logger.error(f"Make sure tls.crt and tls.key keys are present for secret {namespace}/{name}.")
            raise kopf.PermanentError

        try:
            certificate_ocid = create_certificate(
                compartment_id=COMPARTMENT_OCID, 
                secret_name=f"{namespace}_{name}_{uid}", 
                tls_crt=tls_crt, 
                tls_key=tls_key,
                logger=logger)
            if certificate_ocid != None:
                patch.metadata.annotations["oci.oraclecloud.com/certificate-id"] = certificate_ocid
                logger.info(f"OCICertificateCreated | OCI Certificate {certificate_ocid} successfuly created.")
            else:
                raise kopf.TemporaryError("Could not create certificate. Retrying...", delay=60)
        except kopf.TemporaryError:
            raise
        except Exception as e:
            logger.error(f"OCICertificateCreationFail | {e}")
            raise kopf.PermanentError(f"OCICertificateCreationFail | {e}")



@kopf.on.delete("Secret", labels={'sync-to-oci': 'yes'}, retries=3)
def delete_oci_certificate(body, logger, **kwargs):

    oci_certificate_id = body.metadata.annotations.get("oci.oraclecloud.com/certificate-id", None)
    
    if oci_certificate_id != None:
                
        try:
            certificate_deletion_response = schedule_certificate_deletion(
                certificate_id=oci_certificate_id,
                logger=logger)
            if certificate_deletion_response != None:
                logger.info(f"OCICerificateDeleted | OCI Certificate {oci_certificate_id} was scheduled for deletion.")
            else:
                raise kopf.TemporaryError(f"Could not schedule OCI certificate for deletion: {certificate_deletion_response}.")
        except kopf.TemporaryError:
            raise
        except Exception as e:
            logger.error(f"OCICertificateUpdateFail | {e}")
            raise kopf.PermanentError(f"OCICertificateUpdateFail | {e}")
    else:
        logger.info("No OCI certificate associated with the K8 certificate.")

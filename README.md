# OKE Operator to sync Kubernetes Secrets to OCI Certificates

This Kubernetes operator, built using Kopf, is monitoring the Kubernetes TLS Secrets with the label `sync-to-oci: "yes"`, and is attempting to use the `tls.key` and `tls.cer` files to replicate them into OCI Certificates service.

The operator performs the following operations:

1. OCI Certificate creation - when an OKE TLS secret with the required label is created.
2. OCI Certificate renewal - when the OKE TLS secret with the required label is updated.
3. OCI Certificate deleteion - when the OKE TLS secret with the required label is removed.


## Prerequisites:

- [OKE](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengoverview.htm) cluster with managed Kubernetes worker nodes
- Authenticate build environment and OKE with [Oracle Cloud Infrastructure Registry (OCIR)](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionslogintoocir.htm)

## Getting Started

### Preparing the container image

Execute below commands to build and push the container image to OCIR:

  `$ docker build -t <region-key>.ocir.io/<tenancy-namespace>/oci-cert-operator:latest`
  
  `$ docker push <region-key>.ocir.io/<tenancy-namespace>/oci-cert-operator:latest`

### Setup OCI Dynamic Group and Policies

1. Create one dynamic group named `cert-operator` with the following matching rule:
  `instance.compartment.id = '<OKE_cluster_compartment_ocid>'`

    **Note**:

    It's strongly recommended to:
    - use [NodeAffinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) when deploying the operator and take advantage of the [NodePool Kubernetes Labels](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengmodifyingnodepool.htm) for this

    - attach Node Tags to the nodePool where operator should run using Defined Tags (the configured tags and labels will not apply to the exiting nodes in the node pool but only to the ones which will be created in the future)

    - update the dynamic-group match rule to include the defined tags configured before:

    `All {instance.compartment.id='<OKE_cluster_compartment_ocid>', tag.<tag_namespace>.<tag_key>.value='<tag_value>'}`

2. Create operator policies (in the same compartment as the OKE cluster):
  `Allow dynamic-group cert-operator to read clusters in compartment <compartment_name>`
  `Allow dynamic-group cert-operator to manage leaf-certificates in compartment <compartment_name>`
  

### Configure Kubernetes ImagePull Secret

  ```$ kubectl create secret docker-registry ocirsecret --docker-server=<region-key>.ocir.io --docker-username='<tenancy-namespace>/<oci-username>' --docker-password='<oci-auth-token>' --docker-email='<email-address>'```

[More details](https://www.oracle.com/webfolder/technetwork/tutorials/obe/oci/oke-and-registry/index.html#CreateaSecretfortheTutorial)


### Create the Service Account required by the operator

  `$ kubectl apply -f deploy/rbac.yaml`

### Deploy the operator

Update the container image and imagePullSecrets in the `operator.yaml` file and depoy the operator.

  `$ kubectl apply -f deploy/operator.yaml`

## Configuration

The default compartment where certificates will be created is the same compartment where the OKE cluster is created.
It is possible to customize the compartment by setting the container environment variable: `COMPARTMENT_OCID` to the desired compartment_ocid (`ocid1.compartment.oc1..diqq`).

If used to replicate the certificates created by the [cert-manager](https://cert-manager.io/) is necessary to configure the [secretTemplate](https://cert-manager.io/docs/usage/certificate/#creating-certificate-resources) where to define the label: `sync-to-oci: "yes"`

## Limitations

OCI Certificates attached to load balancers or API Gateways and managed by the operator can't be removed when the Kubernetes TLS secret is deleted as the resource is in used.

## License

Copyright (c) 2023 Oracle and/or its affiliates.
Released under the Universal Permissive License v1.0 as shown at <https://oss.oracle.com/licenses/upl/>.
